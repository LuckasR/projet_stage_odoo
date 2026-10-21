from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    miro_trade_id = fields.Many2one(
        'miro.trade', string="Métier (planning)", groups="hr.group_hr_user",
        help="Métier pris en compte dans les équipes et cadences du planning.")

    def _miro_loaded_hourly_cost(self):
        """Coût horaire chargé : salaire ramené à l'heure + charges patronales
        (paramètres de paie de la société)."""
        self.ensure_one()
        company = self.company_id or self.env.company
        hpd = company.miro_hours_per_day or 8.0
        month_days = company.miro_month_days or 26.0
        hourly = {
            'daily': (self.miro_daily_rate or 0.0) / hpd,
            'hourly': self.miro_hourly_rate or 0.0,
            'monthly': (self.miro_monthly_wage or 0.0) / (month_days * hpd),
        }.get(self.miro_pay_type, 0.0)
        if self.miro_social_contributions:
            hourly *= 1 + ((company.miro_cnaps_employer_rate or 0.0)
                           + (company.miro_health_employer_rate or 0.0)) / 100.0
        return hourly

    @api.onchange('miro_trade_id')
    def _onchange_miro_trade_id(self):
        if self.miro_trade_id:
            self.miro_trade = self.miro_trade_id.name
