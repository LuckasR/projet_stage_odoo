from odoo import fields, models


class MiroSiteEquipment(models.Model):
    """Engin ou matériel de chantier (bétonnière, grue, vibreur...) et son
    taux horaire : amortissement et carburant pour un engin à soi, prix de
    location pour un engin loué."""
    _name = 'miro.site.equipment'
    _description = "Matériel de chantier"
    _order = 'name'

    name = fields.Char("Matériel", required=True)
    ownership = fields.Selection([
        ('owned', "En propre"),
        ('rented', "Loué"),
    ], string="Origine", default='owned', required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    hourly_cost = fields.Monetary("Coût horaire", currency_field='currency_id')
    active = fields.Boolean(default=True)
