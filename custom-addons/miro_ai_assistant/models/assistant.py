"""Miro Assistant : la conversation avec le modèle de langage.

Le fournisseur n'est pas figé : tout service qui expose l'API « Chat
Completions » au format OpenAI convient (Groq, OpenAI, Mistral, OpenRouter,
Ollama en local...). L'URL, la clé et le modèle se règlent dans
Paramètres → Miro Assistant.

Une question postée au bot dans Discuss (ou depuis la bulle, qui ouvre la
même conversation) est traitée en tâche de fond (queue_job) :

  1. l'historique récent de la conversation est relu ;
  2. il est envoyé au modèle avec la liste des outils (assistant_tools) ;
  3. tant que le modèle demande un outil, l'outil est exécuté avec les
     droits de l'utilisateur et son résultat lui est renvoyé ;
  4. la réponse finale est postée dans la conversation, au nom du bot.
"""
import json
import logging
import re
import time

import requests
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.tools import html2plaintext

from .assistant_tools import TOOLS, ToolError

_logger = logging.getLogger(__name__)

DEFAULT_URL = 'https://api.groq.com/openai/v1'
DEFAULT_MODEL = 'openai/gpt-oss-20b'
DEFAULT_MAX_TOKENS = 4000
TIMEOUT = 120
HISTORY_MESSAGES = 20
MAX_TOOL_ROUNDS = 8
# Limite de débit (HTTP 429) : on attend ce que demande le fournisseur, s'il
# demande peu (offre gratuite de Groq : 8 000 jetons par minute)
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_MAX_WAIT = 30

SYSTEM_PROMPT = """Tu es Miro Assistant, l'assistant intégré à l'ERP Odoo de Miro Construction, \
entreprise de bâtiment à Madagascar. Tu réponds aux équipes (direction, conducteurs de travaux, \
chefs de chantier) sur leurs chantiers : avancement, retards, phases de construction, \
besoins en matériaux et planning.

Tes chiffres viennent uniquement des outils : interroge-les avant de répondre et ne devine \
jamais un pourcentage, une date ou une quantité. Quand un chantier est cité par son nom, \
retrouve-le avec find_projects (y compris pour une question de suivi : n'invente jamais \
un identifiant de chantier) ; si plusieurs chantiers correspondent, demande lequel. Si \
une information n'existe pas dans la base, dis-le simplement. Tu ne peux rien modifier : \
si on te demande une modification, explique où la faire dans Odoo.

Réponds en français, de façon brève et concrète, comme un collègue qui connaît le chantier : \
commence par la réponse directe (le chiffre demandé), puis deux à cinq points utiles au \
plus (ce qui avance, ce qui bloque, ce qui arrive). Mets en **gras** les chiffres clés. \
Pas de tableaux ni de titres : la réponse s'affiche dans une petite fenêtre de discussion. \
Les dates s'écrivent au format JJ/MM/AAAA."""


class ProviderError(Exception):
    """Réponse d'erreur du fournisseur d'IA, avec son code HTTP."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def markdown_to_html(text):
    """Le strict nécessaire du Markdown que produit le modèle : gras,
    code, listes, paragraphes. Tout le reste est échappé."""
    def inline(line):
        line = str(escape(line))
        line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
        line = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<i>\1</i>', line)
        return re.sub(r'`([^`]+)`', r'<code>\1</code>', line)

    html, para, list_tag = [], [], None

    def flush_para():
        if para:
            html.append('<p>%s</p>' % '<br/>'.join(para))
            para.clear()

    def close_list():
        nonlocal list_tag
        if list_tag:
            html.append('</%s>' % list_tag)
            list_tag = None

    for raw in (text or '').strip().splitlines():
        line = raw.strip()
        bullet = re.match(r'^[-*•]\s+(.*)$', line)
        number = re.match(r'^\d+[.)]\s+(.*)$', line)
        if bullet or number:
            flush_para()
            tag = 'ul' if bullet else 'ol'
            if list_tag != tag:
                close_list()
                html.append('<%s>' % tag)
                list_tag = tag
            html.append('<li>%s</li>' % inline((bullet or number).group(1)))
        elif not line:
            flush_para()
            close_list()
        else:
            close_list()
            heading = re.match(r'^#{1,6}\s+(.*)$', line)
            para.append('<b>%s</b>' % inline(heading.group(1)) if heading else inline(line))
    flush_para()
    close_list()
    return Markup(''.join(html))


class MiroAssistant(models.AbstractModel):
    _name = 'miro.ai.assistant'
    _description = "Miro Assistant"

    # ------------------------------------------------------------------
    # Bot et configuration
    # ------------------------------------------------------------------
    @api.model
    def _bot_partner(self):
        return self.env.ref('miro_ai_assistant.partner_miro_assistant', raise_if_not_found=False) \
            or self.env['res.partner']

    @api.model
    def get_bot_partner_id(self):
        """Appelé par la bulle flottante."""
        return self._bot_partner().id

    @api.model
    def _init_default_params(self):
        """Valeurs par défaut des paramètres, sans écraser un réglage existant
        (sauf l'ancien réglage Claude de la première version du module)."""
        Param = self.env['ir.config_parameter'].sudo()
        model = Param.get_param('miro_ai_assistant.model') or ''
        if not model or model.startswith('claude-'):
            Param.set_param('miro_ai_assistant.model', DEFAULT_MODEL)
            Param.set_param('miro_ai_assistant.reasoning_effort', 'low')
        if not Param.get_param('miro_ai_assistant.api_url'):
            Param.set_param('miro_ai_assistant.api_url', DEFAULT_URL)
        # Restes de la version Claude : paramètre supprimé, clé Anthropic inutilisable ailleurs
        Param.search([('key', '=', 'miro_ai_assistant.effort')]).unlink()
        if (Param.get_param('miro_ai_assistant.api_key') or '').startswith('sk-ant-'):
            Param.set_param('miro_ai_assistant.api_key', False)

    @api.model
    def _config(self):
        param = self.env['ir.config_parameter'].sudo().get_param
        try:
            extra = json.loads(param('miro_ai_assistant.extra_params') or '{}')
        except ValueError:
            extra = {}
        return {
            'url': (param('miro_ai_assistant.api_url') or DEFAULT_URL).rstrip('/'),
            'api_key': param('miro_ai_assistant.api_key') or '',
            'model': param('miro_ai_assistant.model') or DEFAULT_MODEL,
            'reasoning_effort': param('miro_ai_assistant.reasoning_effort') or '',
            'max_tokens': int(param('miro_ai_assistant.max_tokens') or DEFAULT_MAX_TOKENS),
            'extra': extra if isinstance(extra, dict) else {},
        }

    # ------------------------------------------------------------------
    # Déclenchement
    # ------------------------------------------------------------------
    @api.model
    def _schedule_answer(self, channel, message):
        """Le bot « écrit… » tout de suite ; la réponse est calculée en tâche
        de fond pour ne pas bloquer l'envoi du message."""
        self._set_typing(channel, True)
        self.with_delay(description=_("Miro Assistant : réponse dans « %s »") % channel.name,
                        max_retries=1)._answer_job(channel.id, message.id)

    @api.model
    def _set_typing(self, channel, is_typing):
        bot = self._bot_partner()
        member = channel.sudo().channel_member_ids.filtered(lambda m: m.partner_id == bot)
        if member:
            member._notify_typing(is_typing)

    def _answer_job(self, channel_id, message_id):
        channel = self.env['discuss.channel'].browse(channel_id).exists()
        if not channel:
            return
        try:
            answer = self._answer(channel, message_id)
        except Exception as error:  # la conversation doit toujours recevoir une réponse
            _logger.exception("Miro Assistant : échec de la réponse")
            answer = self._error_message(error)
        self._post(channel, answer)

    def _post(self, channel, body):
        bot = self._bot_partner()
        self._set_typing(channel, False)
        channel.with_context(mail_create_nosubscribe=True).sudo().message_post(
            body=body, author_id=bot.id, message_type='comment', subtype_xmlid='mail.mt_comment')

    def _error_message(self, error):
        if isinstance(error, ProviderError) and error.status in (401, 403):
            text = _("La clé API est refusée par le fournisseur d'IA. Un administrateur doit la "
                     "vérifier dans Paramètres → Miro Assistant.")
        elif isinstance(error, ProviderError) and error.status == 429:
            text = _("Trop de questions en même temps (limite du fournisseur d'IA) : réessayez dans une minute.")
        elif isinstance(error, ProviderError) and error.status == 404:
            text = _("Le modèle ou l'adresse de l'API est introuvable : vérifiez Paramètres → Miro Assistant (%s).") % error
        elif isinstance(error, (requests.ConnectionError, requests.Timeout)):
            text = _("Le service d'IA est injoignable (connexion internet du serveur ?). Réessayez plus tard.")
        else:
            text = _("Désolé, je n'ai pas pu répondre (erreur technique : %s).") % error
        return Markup('<p>%s</p>') % text

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------
    def _history(self, channel, upto_message_id):
        """Derniers échanges de la conversation, au format Chat Completions."""
        bot = self._bot_partner()
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
            ('message_type', '=', 'comment'), ('id', '<=', upto_message_id),
        ], order='id desc', limit=HISTORY_MESSAGES)
        history = []
        for message in reversed(messages):
            text = html2plaintext(message.body or '').strip()
            if not text:
                continue
            role = 'assistant' if message.author_id == bot else 'user'
            if role == 'user' and channel.channel_type != 'chat':
                text = "%s : %s" % (message.author_id.name, text)
            if history and history[-1]['role'] == role:
                history[-1]['content'] += "\n\n" + text
            else:
                history.append({'role': role, 'content': text})
        while history and history[0]['role'] == 'assistant':
            history.pop(0)
        return history

    def _system_prompt(self):
        today = fields.Date.context_today(self)
        return "%s\n\nNous sommes le %s. Tu parles avec %s." % (
            SYSTEM_PROMPT, today.strftime('%d/%m/%Y'), self.env.user.name)

    @staticmethod
    def _tool_specs():
        return [{'type': 'function', 'function': {
            'name': tool['name'], 'description': tool['description'], 'parameters': tool['input_schema'],
        }} for tool in TOOLS]

    def _chat(self, config, messages):
        """Un appel POST {url}/chat/completions ; renvoie le premier choix."""
        payload = {
            'model': config['model'],
            'messages': messages,
            'tools': self._tool_specs(),
            'tool_choice': 'auto',
        }
        if 'max_tokens' not in config['extra']:
            payload['max_completion_tokens'] = config['max_tokens']
        if config['reasoning_effort']:
            payload['reasoning_effort'] = config['reasoning_effort']
        payload.update(config['extra'])
        headers = {'Content-Type': 'application/json'}
        if config['api_key']:
            headers['Authorization'] = 'Bearer %s' % config['api_key']
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            response = requests.post('%s/chat/completions' % config['url'], json=payload,
                                     headers=headers, timeout=TIMEOUT)
            wait = self._retry_after(response)
            if response.status_code != 429 or attempt == RATE_LIMIT_RETRIES or wait > RATE_LIMIT_MAX_WAIT:
                break
            _logger.info("Miro Assistant : limite de débit, nouvel essai dans %.1f s", wait)
            time.sleep(wait)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code != 200:
            error = data.get('error') if isinstance(data.get('error'), dict) else {}
            raise ProviderError(response.status_code,
                                error.get('message') or response.text[:300] or response.reason)
        usage = data.get('usage') or {}
        _logger.info("Miro Assistant : %s, %s jetons en entrée, %s en sortie", config['model'],
                     usage.get('prompt_tokens'), usage.get('completion_tokens'))
        return data['choices'][0]

    @staticmethod
    def _retry_after(response):
        """Secondes à attendre avant un nouvel essai, d'après l'en-tête
        Retry-After ou le message (« try again in 7.26s »)."""
        if response.status_code != 429:
            return 0.0
        try:
            return float(response.headers.get('retry-after')) + 0.5
        except (TypeError, ValueError):
            match = re.search(r'try again in (?:(\d+)m)?([\d.]+)s', response.text or '')
            if match:
                return int(match.group(1) or 0) * 60 + float(match.group(2)) + 0.5
        return 5.0

    def _answer(self, channel, message_id):
        config = self._config()
        if not config['api_key'] and 'localhost' not in config['url'] and '127.0.0.1' not in config['url']:
            return Markup('<p>%s</p>') % _(
                "Je ne suis pas encore configuré : un administrateur doit saisir la clé API "
                "dans Paramètres → Miro Assistant.")
        history = self._history(channel, message_id)
        if not history:
            return Markup('<p>%s</p>') % _("Posez-moi une question sur un chantier.")
        messages = [{'role': 'system', 'content': self._system_prompt()}] + history

        for _round in range(MAX_TOOL_ROUNDS):
            try:
                choice = self._chat(config, messages)
            except ProviderError as error:
                # Appel d'outil mal formé par le modèle (Groq : « tool_use_failed ») : on réessaie une fois
                if error.status == 400 and 'tool' in str(error).lower() and not _round:
                    choice = self._chat(config, messages)
                else:
                    raise
            message = choice.get('message') or {}
            tool_calls = message.get('tool_calls') or []
            if not tool_calls:
                break
            messages.append({'role': 'assistant', 'content': message.get('content'), 'tool_calls': tool_calls})
            messages.extend(self._run_tool(call) for call in tool_calls)
        else:
            return Markup('<p>%s</p>') % _("La question demande trop de recherches : pouvez-vous la préciser ?")

        text = (message.get('content') or '').strip()
        if not text and choice.get('finish_reason') == 'length':
            return Markup('<p>%s</p>') % _(
                "La réponse a été coupée (limite de jetons atteinte) : augmentez « Jetons max. » "
                "dans Paramètres → Miro Assistant.")
        return markdown_to_html(text) if text else Markup('<p>%s</p>') % _("Je n'ai pas trouvé de réponse.")

    def _run_tool(self, call):
        tools = self.env['miro.ai.assistant.tools']
        known = {tool['name'] for tool in TOOLS}
        function = call.get('function') or {}
        name = function.get('name')
        try:
            if name not in known:
                raise ToolError(_("Outil inconnu : %s") % name)
            args = json.loads(function.get('arguments') or '{}')
            if not isinstance(args, dict):
                raise ToolError(_("Arguments invalides."))
            # Chaque outil est isolé : une erreur SQL ne casse pas la transaction du job
            with self.env.cr.savepoint():
                result = getattr(tools, name)(**args)
            # JSON compact : moins de jetons consommés chez le fournisseur
            content = json.dumps(result, ensure_ascii=False, default=str, separators=(',', ':'))
        except Exception as error:
            if not isinstance(error, (ToolError, TypeError, ValueError)):
                _logger.exception("Miro Assistant : outil %s", name)
            content = json.dumps({'erreur': str(error)}, ensure_ascii=False)
        return {'role': 'tool', 'tool_call_id': call.get('id'), 'content': content}
