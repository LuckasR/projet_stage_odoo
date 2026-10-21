from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MiroPayslipGenerate(models.TransientModel):
    """Bulletins d'une période pour plusieurs employés, calculés d'un coup.
    Un employé qui a déjà un bulletin non annulé sur la période est ignoré."""
    _name = 'miro.payslip.generate'
    _description = "Génération des bulletins de paie"

    date_from = fields.Date(
        "Du", required=True,
        default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(
        "Au", required=True,
        default=lambda self: fields.Date.today().replace(day=1) + relativedelta(months=1, days=-1))
    employee_ids = fields.Many2many(
        'hr.employee', string="Employés",
        default=lambda self: self.env['hr.employee'].search([
            ('company_id', '=', self.env.company.id)]))
    pay_type = fields.Selection(
        [('daily', "Journalier"), ('hourly', "Horaire"), ('monthly', "Mensuel")],
        string="Seulement le mode", help="Vide : tous les modes de paie.")

    @api.onchange('pay_type')
    def _onchange_pay_type(self):
        domain = [('company_id', '=', self.env.company.id)]
        if self.pay_type:
            domain.append(('miro_pay_type', '=', self.pay_type))
        self.employee_ids = self.env['hr.employee'].search(domain)

    def action_generate(self):
        self.ensure_one()
        if not self.employee_ids:
            raise UserError(_("Sélectionnez au moins un employé."))
        Payslip = self.env['miro.payslip']
        existing = Payslip.search([
            ('employee_id', 'in', self.employee_ids.ids), ('state', '!=', 'cancel'),
            ('date_from', '<=', self.date_to), ('date_to', '>=', self.date_from),
        ]).employee_id
        employees = self.employee_ids - existing
        slips = Payslip.create([{
            'employee_id': employee.id, 'company_id': employee.company_id.id,
            'date_from': self.date_from, 'date_to': self.date_to,
        } for employee in employees])
        errors = []
        for slip in slips:
            try:
                with self.env.cr.savepoint():
                    slip._compute_sheet()
            except UserError as exc:
                errors.append("%s : %s" % (slip.employee_id.name, exc.args[0]))
        action = {
            'type': 'ir.actions.act_window', 'name': _("Bulletins générés"),
            'res_model': 'miro.payslip', 'view_mode': 'tree,form',
            'domain': [('id', 'in', slips.ids)],
        }
        if errors or existing:
            message = []
            if existing:
                message.append(_("%d employé(s) ont déjà un bulletin sur la période.") % len(existing))
            if errors:
                message.append(_("Bulletins à compléter :\n%s") % "\n".join(errors))
            slips[:1].message_post(body="<br/>".join(message).replace("\n", "<br/>")) if slips else None
        return action
