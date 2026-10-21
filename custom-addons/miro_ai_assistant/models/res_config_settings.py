import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .assistant import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, DEFAULT_URL


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    miro_ai_api_url = fields.Char(
        "URL de l'API", config_parameter='miro_ai_assistant.api_url', default=DEFAULT_URL,
        help="Adresse de base d'une API compatible OpenAI (Chat Completions), sans "
             "« /chat/completions ». Ex. : https://api.groq.com/openai/v1, "
             "https://api.openai.com/v1, https://api.mistral.ai/v1, "
             "https://openrouter.ai/api/v1, http://localhost:11434/v1 (Ollama).")
    miro_ai_api_key = fields.Char(
        "Clé API", config_parameter='miro_ai_assistant.api_key',
        help="Clé du fournisseur (Groq : console.groq.com → API Keys). Inutile pour un "
             "modèle local (Ollama).")
    miro_ai_model = fields.Char(
        "Modèle", config_parameter='miro_ai_assistant.model', default=DEFAULT_MODEL,
        help="Nom exact du modèle chez le fournisseur, ex. openai/gpt-oss-20b, "
             "openai/gpt-oss-120b, llama-3.3-70b-versatile. Il doit savoir appeler des "
             "outils (« tool use / function calling »).")
    miro_ai_reasoning_effort = fields.Selection(
        [('low', "Faible"), ('medium', "Moyenne"), ('high', "Élevée")],
        string="Réflexion", config_parameter='miro_ai_assistant.reasoning_effort',
        help="Paramètre « reasoning_effort », pour les modèles qui raisonnent (gpt-oss...). "
             "Laisser vide pour les autres modèles, qui le refuseraient.")
    miro_ai_max_tokens = fields.Integer(
        "Jetons max. par réponse", config_parameter='miro_ai_assistant.max_tokens',
        default=DEFAULT_MAX_TOKENS)
    miro_ai_extra_params = fields.Char(
        "Paramètres supplémentaires (JSON)", config_parameter='miro_ai_assistant.extra_params',
        help="Ajoutés tels quels à chaque requête, ex. {\"temperature\": 0.2}. Pour un "
             "fournisseur qui n'accepte que l'ancien nom : {\"max_tokens\": 2000}.")

    @api.constrains('miro_ai_extra_params')
    def _check_miro_ai_extra_params(self):
        for settings in self.filtered('miro_ai_extra_params'):
            try:
                value = json.loads(settings.miro_ai_extra_params)
            except ValueError:
                value = None
            if not isinstance(value, dict):
                raise ValidationError("Paramètres supplémentaires : un objet JSON est attendu, ex. {\"temperature\": 0.2}.")
