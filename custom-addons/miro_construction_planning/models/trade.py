from odoo import api, fields, models


class MiroTrade(models.Model):
    """Métier du chantier. Son coût horaire chargé et son effectif se
    calculent depuis les employés qui l'exercent ; un coût saisi à la main
    les remplace (métier sous-traité, ou sans employé encore)."""
    _name = 'miro.trade'
    _description = "Métier"
    _order = 'sequence, name'

    name = fields.Char("Métier", required=True, translate=True)
    code = fields.Char("Code")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    employee_ids = fields.One2many('hr.employee', 'miro_trade_id', string="Employés",
                                   groups="hr.group_hr_user")
    employee_count = fields.Integer(
        "Employés actuels", compute='_compute_from_employees',
        help="Employés actifs exerçant ce métier (pour information : le planning "
             "propose son propre effectif).")
    computed_hourly_cost = fields.Monetary(
        "Coût horaire calculé", compute='_compute_from_employees',
        help="Moyenne des coûts horaires chargés des employés du métier : "
             "salaire ramené à l'heure + charges patronales.")
    manual_hourly_cost = fields.Monetary(
        "Coût horaire de référence",
        help="Coût horaire chargé utilisé pour chiffrer le planning, sans dépendre "
             "des employés saisis. Vide : moyenne des employés du métier.")
    hourly_cost = fields.Monetary(
        "Coût horaire chargé", compute='_compute_from_employees',
        help="Coût imposé s'il est renseigné, sinon coût calculé.")

    _sql_constraints = [('name_uniq', 'unique(name, company_id)', "Ce métier existe déjà.")]

    @api.depends('employee_ids.active', 'manual_hourly_cost',
                 'employee_ids.miro_pay_type', 'employee_ids.miro_daily_rate',
                 'employee_ids.miro_hourly_rate', 'employee_ids.miro_monthly_wage')
    def _compute_from_employees(self):
        # Les champs de paie sont réservés aux RH : le coût d'un métier doit
        # pourtant se lire depuis le planning.
        for trade in self:
            employees = trade.sudo().employee_ids.filtered('active')
            costs = [c for c in (e._miro_loaded_hourly_cost() for e in employees) if c]
            trade.employee_count = len(employees)
            trade.computed_hourly_cost = sum(costs) / len(costs) if costs else 0.0
            trade.hourly_cost = trade.manual_hourly_cost or trade.computed_hourly_cost
