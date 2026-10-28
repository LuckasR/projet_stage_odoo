import hashlib
import secrets

from odoo import api, fields, models


class MiroMobileDevice(models.Model):
    """Téléphone connecté à l'application SuiviChantier. Le jeton ne quitte
    Odoo qu'une fois, à la connexion : seul son empreinte est gardée. Il ne
    périme pas (un chantier peut rester des jours sans réseau) ; on révoque
    un téléphone perdu en l'archivant."""
    _name = 'miro.mobile.device'
    _description = "Appareil mobile"
    _order = 'last_seen desc, id desc'

    name = fields.Char("Appareil", required=True)
    user_id = fields.Many2one(
        'res.users', string="Utilisateur", required=True, ondelete='cascade', index=True)
    token_hash = fields.Char(required=True, index=True, copy=False, groups='base.group_system')
    last_seen = fields.Datetime("Dernière synchronisation", readonly=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('token_hash_uniq', 'unique(token_hash)', "Jeton déjà attribué."),
    ]

    @api.model
    def _hash(self, token):
        return hashlib.sha256(token.encode()).hexdigest()

    @api.model
    def _issue(self, user, name):
        """Crée l'appareil et renvoie son jeton en clair."""
        token = secrets.token_urlsafe(32)
        self.sudo().create({'name': name, 'user_id': user.id, 'token_hash': self._hash(token)})
        return token

    @api.model
    def _from_token(self, token):
        if not token:
            return self.browse()
        return self.sudo().search([('token_hash', '=', self._hash(token))], limit=1)

    def action_revoke(self):
        self.active = False
