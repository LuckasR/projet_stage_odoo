from odoo import fields, models


class ConstructionPhaseTemplateLine(models.Model):
    _inherit = 'construction.phase.template.line'

    min_lag_days = fields.Float(
        "Délai après la phase précédente (j)",
        help="Temps d'attente technique minimal après la fin de la phase dont "
             "celle-ci dépend : séchage, prise du béton avant décoffrage (7 j)...")

    def _compute_hours(self, element):
        """Heures prévues (heures-personnes) : durée de l'équipe retenue ×
        son effectif. Sans cadence d'équipe, le rendement du gabarit."""
        self.ensure_one()
        rate = self.env['miro.crew.rate']._rate_for(self.phase_type, element.element_type_id)
        if rate and self.qty_key:
            qty = getattr(element, 'qty_%s' % self.qty_key, 0.0) or 0.0
            return qty / rate.rate * rate.headcount
        return super()._compute_hours(element)
