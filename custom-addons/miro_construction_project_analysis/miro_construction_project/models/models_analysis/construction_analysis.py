import json
import logging
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
QTY_KEYS = ('beton_m3', 'acier_kg', 'coffrage_m2')
TIMEOUT_MINUTES = 30


class ConstructionAnalysis(models.Model):
    _name = 'construction.analysis'
    _description = "Analyse de plan"
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(compute='_compute_name', store=True)
    file_id = fields.Many2one(
        'construction.file', string="Plan", required=True, ondelete='cascade')
    project_id = fields.Many2one(
        'project.project', related='file_id.project_id', store=True, readonly=True)
    revision = fields.Char("Indice de révision")
    engine = fields.Char("Moteur", default='external')
    state = fields.Selection(
        [('draft', "À lancer"),
         ('running', "En cours"),
         ('done', "Terminée"),
         ('failed', "Échec")],
        default='draft', required=True, tracking=True)
    started_at = fields.Datetime("Début")
    finished_at = fields.Datetime("Fin")
    error_log = fields.Text("Journal d'erreur")
    payload_json = fields.Text(
        "Résultat JSON",
        help="Dernier JSON reçu du service d'analyse. Peut aussi être collé "
             "à la main pour tester la chaîne sans service externe.")
    draft_ids = fields.One2many('construction.element.draft', 'analysis_id', string="Brouillons")
    draft_count = fields.Integer(compute='_compute_draft_count')

    @api.depends('file_id', 'revision')
    def _compute_name(self):
        for rec in self:
            rec.name = "%s%s" % (
                rec.file_id.display_name or _("Analyse"),
                " (%s)" % rec.revision if rec.revision else "")

    @api.depends('draft_ids')
    def _compute_draft_count(self):
        for rec in self:
            rec.draft_count = len(rec.draft_ids)

    # ------------------------------------------------------------------
    # Lancement de l'analyse (service externe)
    # ------------------------------------------------------------------
    def _get_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key)

    def action_start(self):
        self.ensure_one()
        if self.state == 'running':
            raise UserError(_("Cette analyse est déjà en cours."))
        url = self._get_param('miro_construction.analysis_url')
        if not url:
            raise UserError(_(
                "Aucun service d'analyse configuré (paramètre système "
                "« miro_construction.analysis_url »).\n"
                "Pour tester, collez un JSON dans l'onglet « Résultat » puis "
                "utilisez « Importer le JSON »."))
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', 'construction.file'),
            ('res_id', '=', self.file_id.id)], limit=1)
        if not attachment:
            raise UserError(_("Aucun fichier joint au plan sélectionné."))

        base_url = self._get_param('web.base.url')
        access_token = attachment.generate_access_token()[0]
        payload = {
            'analysis_id': self.id,
            'schema_version': SCHEMA_VERSION,
            'file_url': "%s/web/content/%s?access_token=%s&download=true" % (
                base_url, attachment.id, access_token),
            'file_name': attachment.name,
            'callback_url': "%s/construction/analysis/result" % base_url,
        }
        headers = {'X-Miro-Token': self._get_param('miro_construction.api_token') or ''}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            _logger.exception("Envoi de l'analyse %s impossible", self.id)
            self.write({'state': 'failed', 'error_log': str(exc),
                        'finished_at': fields.Datetime.now()})
            return True
        self.write({'state': 'running', 'started_at': fields.Datetime.now(),
                    'finished_at': False, 'error_log': False})
        return True

    def action_retry(self):
        self.write({'state': 'draft'})
        return self.action_start()

    @api.model
    def _cron_timeout_running(self):
        limit = fields.Datetime.now() - timedelta(minutes=TIMEOUT_MINUTES)
        stuck = self.search([('state', '=', 'running'), ('started_at', '<', limit)])
        stuck.write({
            'state': 'failed',
            'finished_at': fields.Datetime.now(),
            'error_log': _("Délai dépassé (%s min) sans réponse du service d'analyse.")
                         % TIMEOUT_MINUTES,
        })

    # ------------------------------------------------------------------
    # Réception du résultat
    # ------------------------------------------------------------------
    def action_import_payload(self):
        """Importe le JSON collé dans le champ payload_json (test manuel)."""
        self.ensure_one()
        if not self.payload_json:
            raise UserError(_("Le champ « Résultat JSON » est vide."))
        try:
            data = json.loads(self.payload_json)
        except ValueError as exc:
            raise UserError(_("JSON invalide : %s") % exc)
        self._process_result(data)
        return True

    def _process_result(self, data):
        """Crée ou met à jour les brouillons à partir du JSON du service.

        Ne crée jamais d'élément ni de tâche : uniquement des brouillons.
        """
        self.ensure_one()
        if not isinstance(data, dict):
            raise ValidationError(_("Le résultat doit être un objet JSON."))

        if data.get('status') == 'failed':
            self.write({
                'state': 'failed',
                'finished_at': fields.Datetime.now(),
                'error_log': data.get('error') or _("Échec signalé par le service d'analyse."),
            })
            return

        if data.get('schema_version', SCHEMA_VERSION) != SCHEMA_VERSION:
            raise ValidationError(_(
                "Version de schéma non supportée : %s (attendu : %s).")
                % (data.get('schema_version'), SCHEMA_VERSION))
        items = data.get('elements')
        if not isinstance(items, list):
            raise ValidationError(_("Le champ « elements » doit être une liste."))

        types = {t.code: t for t in self.env['construction.element.type'].search([])}
        project_elements = {}
        if self.project_id:
            project_elements = {
                e.key: e for e in self.env['construction.element'].search([
                    ('work_id.project_id', '=', self.project_id.id),
                    ('key', '!=', False)])
            }
        existing_drafts = {d.key: d for d in self.draft_ids}

        to_create, seen, errors = [], set(), []
        for item in items:
            key = str(item.get('key') or '').strip()
            if not key or key in seen:
                errors.append(_("Élément ignoré (clé vide ou en double) : %s") % item)
                continue
            seen.add(key)

            code = (item.get('type') or '').strip().lower()
            etype = types.get(code)
            quantities = {k: float(v) for k, v in (item.get('quantities') or {}).items()
                          if isinstance(v, (int, float))}
            source = item.get('source') or {}
            element = project_elements.get(key)
            vals = {
                'key': key,
                'type_code': code,
                'type_id': etype.id if etype else False,
                'quantities': quantities,
                'dimensions': item.get('dimensions') or {},
                'confidence': float(item.get('confidence') or 0.0),
                'source_page': source.get('page') or 0,
                'source_bbox': source.get('bbox') or [],
                'element_id': element.id if element else False,
                'change_type': self._detect_change(element, quantities),
                'issue': False if etype else _("Type « %s » inconnu") % code,
            }
            draft = existing_drafts.get(key)
            if draft:
                if draft.state in ('validated', 'generated'):
                    continue  # on ne touche jamais à ce qui est déjà validé
                draft.write(vals)
            else:
                to_create.append(dict(vals, analysis_id=self.id))

        if to_create:
            self.env['construction.element.draft'].create(to_create)

        missing = [k for k in project_elements if k not in seen]
        if missing:
            self.message_post(body=_(
                "Éléments existants absents de cette analyse (à vérifier, "
                "jamais supprimés automatiquement) : %s") % ', '.join(sorted(missing)))

        self.write({
            'state': 'done',
            'finished_at': fields.Datetime.now(),
            'error_log': "\n".join(errors) or False,
        })

    @api.model
    def _detect_change(self, element, quantities):
        if not element:
            return 'new'
        for key in QTY_KEYS:
            if abs((getattr(element, 'qty_%s' % key, 0.0) or 0.0)
                   - (quantities.get(key) or 0.0)) > 1e-6:
                return 'modified'
        return 'unchanged'

    # ------------------------------------------------------------------
    # Actions de validation / génération en masse
    # ------------------------------------------------------------------
    def action_validate_confident(self, threshold=0.9):
        for rec in self:
            rec.draft_ids.filtered(
                lambda d: d.state == 'pending' and d.type_id
                and d.confidence >= threshold).write({'state': 'validated'})

    def action_generate(self):
        self.ensure_one()
        self.draft_ids.action_generate()

    def action_view_drafts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Brouillons"),
            'res_model': 'construction.element.draft',
            'view_mode': 'tree,form',
            'domain': [('analysis_id', '=', self.id)],
            'context': {'default_analysis_id': self.id},
        }
