import math
from collections import defaultdict
from datetime import datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .hr_employee import PAY_TYPES

CATEGORIES = [
    ('gain', "Gain"),
    ('deduction', "Retenue"),
    ('employer', "Charge patronale"),
]


class MiroPayslip(models.Model):
    """Bulletin de paie d'un employé sur une période, calculé à partir de ses
    présences (hr.attendance) et de son mode de paie.

    Les lignes calculées sont refaites à chaque calcul ; les lignes saisies à
    la main (primes, indemnités, avances) sont conservées."""
    _name = 'miro.payslip'
    _description = "Bulletin de paie"
    _inherit = ['mail.thread']
    _order = 'date_from desc, employee_id'

    name = fields.Char("Référence", default="/", copy=False, readonly=True)
    employee_id = fields.Many2one(
        'hr.employee', string="Employé", required=True, tracking=True,
        domain="[('company_id', 'in', (company_id, False))]")
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(
        "Du", required=True,
        default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(
        "Au", required=True,
        default=lambda self: fields.Date.today().replace(day=1) + relativedelta(months=1, days=-1))
    payment_date = fields.Date("Date de paiement")
    state = fields.Selection([
        ('draft', "Brouillon"),
        ('done', "Validé"),
        ('paid', "Payé"),
        ('cancel', "Annulé"),
    ], default='draft', required=True, tracking=True, string="État")
    note = fields.Text("Note")

    # Instantané du contrat au moment du calcul : le bulletin reste juste
    # même si le taux de l'employé change ensuite.
    pay_type = fields.Selection(PAY_TYPES, string="Mode de paie", readonly=True)
    rate = fields.Monetary("Taux", readonly=True,
                           help="Taux journalier, taux horaire ou salaire mensuel.")
    job_label = fields.Char("Emploi", readonly=True)

    # Présences de la période
    worked_days = fields.Float("Jours travaillés", readonly=True, digits=(16, 2))
    worked_hours = fields.Float("Heures travaillées", readonly=True, digits=(16, 2))
    overtime_hours = fields.Float("Heures supplémentaires", readonly=True, digits=(16, 2))
    expected_days = fields.Float("Jours ouvrés", readonly=True, digits=(16, 2))
    absent_days = fields.Float("Jours d'absence", readonly=True, digits=(16, 2))
    attendance_count = fields.Integer("Pointages", readonly=True)

    line_ids = fields.One2many('miro.payslip.line', 'payslip_id', string="Rubriques", copy=True)
    gross = fields.Monetary("Salaire brut", compute='_compute_totals', store=True)
    total_deductions = fields.Monetary("Total retenues", compute='_compute_totals', store=True)
    net = fields.Monetary("Net à payer", compute='_compute_totals', store=True, tracking=True)
    employer_charges = fields.Monetary("Charges patronales", compute='_compute_totals', store=True)
    total_cost = fields.Monetary(
        "Coût employeur", compute='_compute_totals', store=True,
        help="Salaire brut + charges patronales.")
    taxable = fields.Monetary("Revenu imposable", readonly=True)

    _sql_constraints = [
        ('dates_check', 'CHECK(date_from <= date_to)',
         "La date de début doit précéder la date de fin."),
    ]

    @api.depends('line_ids.amount', 'line_ids.category')
    def _compute_totals(self):
        for slip in self:
            lines = slip.line_ids
            slip.gross = sum(lines.filtered(lambda l: l.category == 'gain').mapped('amount'))
            slip.total_deductions = sum(
                lines.filtered(lambda l: l.category == 'deduction').mapped('amount'))
            slip.employer_charges = sum(
                lines.filtered(lambda l: l.category == 'employer').mapped('amount'))
            slip.net = slip.gross - slip.total_deductions
            slip.total_cost = slip.gross + slip.employer_charges

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('miro.payslip') or '/'
        return super().create(vals_list)

    def _compute_display_name(self):
        for slip in self:
            slip.display_name = "%s — %s" % (slip.name, slip.employee_id.name or '')

    # ------------------------------------------------------------------
    # Calcul
    # ------------------------------------------------------------------
    def action_compute(self):
        for slip in self:
            if slip.state != 'draft':
                raise UserError(_("Seul un bulletin brouillon peut être recalculé (%s).") % slip.name)
            slip._compute_sheet()
        return True

    def _attendance_summary(self):
        """Heures par jour de la période, d'après les pointages terminés."""
        self.ensure_one()
        start = datetime.combine(self.date_from, time.min)
        stop = datetime.combine(self.date_to + timedelta(days=1), time.min)
        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('check_in', '>=', start), ('check_in', '<', stop),
            ('check_out', '!=', False),
        ])
        # Jour de travail dans le fuseau de l'employé, pas en UTC
        local = self.with_context(tz=self.employee_id.tz or self.env.user.tz or 'UTC')
        per_day = defaultdict(float)
        for att in attendances:
            check_in = fields.Datetime.context_timestamp(local, att.check_in)
            per_day[check_in.date()] += att.worked_hours
        return per_day, len(attendances)

    def _expected_days(self):
        """Jours ouvrés de la période d'après le calendrier de l'employé."""
        self.ensure_one()
        employee = self.employee_id
        if not employee.resource_calendar_id:
            return 0.0
        start = datetime.combine(self.date_from, time.min)
        stop = datetime.combine(self.date_to, time.max)
        data = employee._get_work_days_data_batch(start, stop, compute_leaves=False)
        return data.get(employee.id, {}).get('days', 0.0)

    def _compute_sheet(self):
        self.ensure_one()
        company = self.company_id
        employee = self.employee_id
        hpd = company.miro_hours_per_day or 8.0
        month_days = company.miro_month_days or 26.0
        majoration = 1.0 + (company.miro_overtime_rate or 0.0) / 100.0

        per_day, att_count = self._attendance_summary()
        days = float(sum(1 for h in per_day.values() if h > 0))
        hours = sum(per_day.values())
        overtime = sum(max(h - hpd, 0.0) for h in per_day.values())
        expected = self._expected_days()
        absent = max(expected - days, 0.0)

        pay_type = employee.miro_pay_type or 'daily'
        rate = {'daily': employee.miro_daily_rate, 'hourly': employee.miro_hourly_rate,
                'monthly': employee.miro_monthly_wage}[pay_type]
        if not rate:
            raise UserError(_("Renseignez le taux de paie de %s (fiche employé, onglet "
                              "« Paie »).") % employee.name)

        Line = self.env['miro.payslip.line']
        manual = self.line_ids.filtered('manual')
        (self.line_ids - manual).unlink()
        lines = []

        def add(code, name, category, quantity, unit, amount, seq, base=0.0, pct=0.0):
            lines.append({'payslip_id': self.id, 'code': code, 'name': name,
                          'category': category, 'quantity': quantity, 'unit_amount': unit,
                          'base': base, 'rate_pct': pct, 'amount': amount, 'sequence': seq,
                          'manual': False})

        # --- Salaire de base -------------------------------------------
        if pay_type == 'daily':
            add('BASE', _("Journées travaillées"), 'gain', days, rate, days * rate, 10)
            hourly_equiv = rate / hpd
        elif pay_type == 'hourly':
            normal = max(hours - overtime, 0.0)
            add('BASE', _("Heures normales"), 'gain', normal, rate, normal * rate, 10)
            hourly_equiv = rate
        else:
            add('BASE', _("Salaire de base mensuel"), 'gain', 1, rate, rate, 10)
            day_rate = rate / month_days
            if company.miro_deduct_absences and absent:
                add('ABS', _("Absences non rémunérées"), 'gain', -absent, day_rate,
                    -absent * day_rate, 12)
            hourly_equiv = day_rate / hpd

        if overtime:
            unit = hourly_equiv * majoration
            add('HSUP', _("Heures supplémentaires (+%s %%)") % ('%g' % company.miro_overtime_rate),
                'gain', overtime, unit, overtime * unit, 20)

        gross = sum(l['amount'] for l in lines if l['category'] == 'gain') \
            + sum(manual.filtered(lambda l: l.category == 'gain').mapped('amount'))

        # --- Cotisations sociales --------------------------------------
        def capped(ceiling):
            return min(gross, ceiling) if ceiling else gross

        employee_contrib = 0.0
        if employee.miro_social_contributions and gross > 0:
            for code, label, ceiling, emp_rate, empr_rate in (
                    ('CNAPS', "CNaPS", company.miro_cnaps_ceiling,
                     company.miro_cnaps_employee_rate, company.miro_cnaps_employer_rate),
                    ('SANTE', company.miro_health_label or _("Santé"), company.miro_health_ceiling,
                     company.miro_health_employee_rate, company.miro_health_employer_rate)):
                base = capped(ceiling)
                if emp_rate:
                    amount = base * emp_rate / 100.0
                    employee_contrib += amount
                    add(code, _("Cotisation %s salariale") % label, 'deduction', 0, 0, amount,
                        30, base=base, pct=emp_rate)
                if empr_rate:
                    add(code + '_P', _("Cotisation %s patronale") % label, 'employer', 0, 0,
                        base * empr_rate / 100.0, 60, base=base, pct=empr_rate)

        # --- IRSA ------------------------------------------------------
        # Revenu imposable arrondi à la centaine inférieure
        taxable = max(math.floor((gross - employee_contrib) / 100.0) * 100.0, 0.0)
        irsa = 0.0
        if employee.miro_subject_irsa and taxable > 0:
            Bracket = self.env['miro.irsa.bracket']
            exempt = Bracket.search([('company_id', '=', company.id), ('rate', '=', 0)],
                                    order='amount_to desc', limit=1).amount_to or 0.0
            if taxable > exempt:
                irsa = Bracket._tax_for(company, taxable)
                irsa -= employee.miro_dependents * company.miro_irsa_dependent_reduction
                irsa = max(irsa, company.miro_irsa_minimum)
        if irsa:
            add('IRSA', _("IRSA"), 'deduction', 0, 0, irsa, 40, base=taxable)

        Line.create(lines)
        self.write({
            'pay_type': pay_type, 'rate': rate,
            'job_label': employee.job_title or employee.miro_trade or employee.job_id.name or False,
            'worked_days': days, 'worked_hours': hours, 'overtime_hours': overtime,
            'expected_days': expected, 'absent_days': absent,
            'attendance_count': att_count, 'taxable': taxable,
        })

    # ------------------------------------------------------------------
    # États
    # ------------------------------------------------------------------
    def action_done(self):
        for slip in self.filtered(lambda s: s.state == 'draft'):
            if not slip.line_ids:
                slip._compute_sheet()
        self.filtered(lambda s: s.state == 'draft').write({'state': 'done'})

    def action_paid(self):
        self.filtered(lambda s: s.state == 'done').write({
            'state': 'paid', 'payment_date': fields.Date.today()})

    def action_draft(self):
        self.filtered(lambda s: s.state in ('done', 'cancel')).write({'state': 'draft'})

    def action_cancel(self):
        self.filtered(lambda s: s.state != 'paid').write({'state': 'cancel'})

    def action_print(self):
        return self.env.ref('miro_hr_paie.action_report_payslip').report_action(self)

    def unlink(self):
        if self.filtered(lambda s: s.state in ('done', 'paid')):
            raise UserError(_("Un bulletin validé ou payé ne peut pas être supprimé : annulez-le."))
        return super().unlink()

    def _amount_in_words(self):
        self.ensure_one()
        return self.currency_id.amount_to_text(self.net)


class MiroPayslipLine(models.Model):
    _name = 'miro.payslip.line'
    _description = "Rubrique de bulletin de paie"
    _order = 'sequence, id'

    payslip_id = fields.Many2one('miro.payslip', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='payslip_id.currency_id')
    sequence = fields.Integer(default=50)
    code = fields.Char("Code")
    name = fields.Char("Rubrique", required=True)
    category = fields.Selection(CATEGORIES, string="Nature", required=True, default='gain')
    quantity = fields.Float("Nombre", digits=(16, 2))
    unit_amount = fields.Monetary("Taux unitaire")
    base = fields.Monetary("Base")
    rate_pct = fields.Float("Taux (%)", digits=(16, 2))
    amount = fields.Monetary("Montant", required=True)
    manual = fields.Boolean(
        "Saisie manuelle", default=True,
        help="Conservée au recalcul du bulletin (prime, indemnité, avance...).")

    @api.onchange('quantity', 'unit_amount')
    def _onchange_quantity(self):
        if self.quantity and self.unit_amount:
            self.amount = self.quantity * self.unit_amount
