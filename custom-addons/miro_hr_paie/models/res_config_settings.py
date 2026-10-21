from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    miro_hours_per_day = fields.Float(related='company_id.miro_hours_per_day', readonly=False)
    miro_month_days = fields.Float(related='company_id.miro_month_days', readonly=False)
    miro_overtime_rate = fields.Float(related='company_id.miro_overtime_rate', readonly=False)
    miro_deduct_absences = fields.Boolean(related='company_id.miro_deduct_absences', readonly=False)
    miro_cnaps_employee_rate = fields.Float(related='company_id.miro_cnaps_employee_rate', readonly=False)
    miro_cnaps_employer_rate = fields.Float(related='company_id.miro_cnaps_employer_rate', readonly=False)
    miro_cnaps_ceiling = fields.Monetary(related='company_id.miro_cnaps_ceiling', readonly=False)
    miro_health_label = fields.Char(related='company_id.miro_health_label', readonly=False)
    miro_health_employee_rate = fields.Float(related='company_id.miro_health_employee_rate', readonly=False)
    miro_health_employer_rate = fields.Float(related='company_id.miro_health_employer_rate', readonly=False)
    miro_health_ceiling = fields.Monetary(related='company_id.miro_health_ceiling', readonly=False)
    miro_irsa_minimum = fields.Monetary(related='company_id.miro_irsa_minimum', readonly=False)
    miro_irsa_dependent_reduction = fields.Monetary(
        related='company_id.miro_irsa_dependent_reduction', readonly=False)
