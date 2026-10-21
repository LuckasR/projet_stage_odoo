from odoo import api, fields, models


class MiroIrsaBracket(models.Model):
    """Tranche du barème de l'impôt sur les revenus salariaux (IRSA). Le
    taux s'applique à la part du revenu imposable comprise dans la tranche."""
    _name = 'miro.irsa.bracket'
    _description = "Tranche du barème IRSA"
    _order = 'company_id, amount_from'

    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company,
                                 ondelete='cascade')
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount_from = fields.Monetary("De", required=True)
    amount_to = fields.Monetary("À", help="Vide ou 0 : sans limite.")
    rate = fields.Float("Taux (%)", required=True)

    @api.model
    def _tax_for(self, company, base):
        """Impôt brut, tranche par tranche."""
        tax = 0.0
        for bracket in self.search([('company_id', '=', company.id)]):
            upper = bracket.amount_to or float('inf')
            if base > bracket.amount_from:
                tax += (min(base, upper) - bracket.amount_from) * bracket.rate / 100.0
        return tax
