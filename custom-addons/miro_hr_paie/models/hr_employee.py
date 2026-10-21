from odoo import _, fields, models

PAY_TYPES = [
    ('daily', "Journalier"),
    ('hourly', "Horaire"),
    ('monthly', "Mensuel"),
]


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    miro_pay_type = fields.Selection(
        PAY_TYPES, string="Mode de paie", default='daily', groups="hr.group_hr_user",
        help="Journalier : journées de présence × taux journalier.\n"
             "Horaire : heures de présence × taux horaire.\n"
             "Mensuel : salaire fixe, absences déduites selon les paramètres.")
    miro_daily_rate = fields.Monetary(
        "Taux journalier", currency_field='miro_currency_id', groups="hr.group_hr_user")
    miro_hourly_rate = fields.Monetary(
        "Taux horaire", currency_field='miro_currency_id', groups="hr.group_hr_user")
    miro_monthly_wage = fields.Monetary(
        "Salaire mensuel", currency_field='miro_currency_id', groups="hr.group_hr_user")
    miro_currency_id = fields.Many2one(related='company_id.currency_id', string="Devise")
    miro_trade = fields.Char(
        "Métier", groups="hr.group_hr_user",
        help="Maçon, coffreur, ferrailleur, manœuvre, chef d'équipe...")
    miro_cnaps_number = fields.Char("N° CNaPS", groups="hr.group_hr_user")
    miro_dependents = fields.Integer(
        "Personnes à charge", groups="hr.group_hr_user",
        help="Chacune réduit l'IRSA du montant fixé dans les paramètres de paie.")
    miro_social_contributions = fields.Boolean(
        "Soumis aux cotisations sociales", default=True, groups="hr.group_hr_user")
    miro_subject_irsa = fields.Boolean(
        "Soumis à l'IRSA", default=True, groups="hr.group_hr_user")
    miro_payslip_ids = fields.One2many(
        'miro.payslip', 'employee_id', string="Bulletins de paie", groups="hr.group_hr_user")
    miro_payslip_count = fields.Integer(
        compute='_compute_miro_payslip_count', groups="hr.group_hr_user")

    def _compute_miro_payslip_count(self):
        for employee in self:
            employee.miro_payslip_count = len(employee.miro_payslip_ids)

    def action_view_miro_payslips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Bulletins de paie — %s") % self.name,
            'res_model': 'miro.payslip',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
