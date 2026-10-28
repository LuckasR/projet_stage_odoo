from odoo import fields, models


class MiroMobileOp(models.Model):
    """Opération reçue du téléphone et déjà appliquée. Si le téléphone la
    renvoie (réponse perdue dans une coupure réseau), on rend le même
    résultat sans l'appliquer une seconde fois."""
    _name = 'miro.mobile.op'
    _description = "Opération mobile appliquée"
    _order = 'id desc'

    uuid = fields.Char(required=True, index=True)
    device_id = fields.Many2one('miro.mobile.device', ondelete='set null')
    kind = fields.Char("Opération")
    result = fields.Text("Résultat (JSON)")

    _sql_constraints = [
        ('uuid_uniq', 'unique(uuid)', "Opération déjà appliquée."),
    ]
