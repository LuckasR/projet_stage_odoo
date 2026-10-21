from odoo import api, fields, models

QTY_FIELDS = ('qty_beton_m3', 'qty_acier_kg', 'qty_coffrage_m2', 'qty_surface_m2')


class ProjectTask(models.Model):
    """Main-d'œuvre prévue d'une phase, d'après la cadence de l'équipe
    retenue. Une phase commencée garde ses valeurs : elles ont pu servir à
    planifier."""
    _inherit = 'project.task'

    miro_crew_rate_id = fields.Many2one('miro.crew.rate', string="Cadence retenue", readonly=True)
    miro_crew_id = fields.Many2one('miro.crew', string="Équipe", readonly=True)
    miro_headcount = fields.Integer("Effectif", readonly=True)
    miro_duration_hours = fields.Float(
        "Durée (h)", readonly=True, digits=(16, 2),
        help="Temps de l'équipe sur la phase : quantité ÷ cadence.")
    miro_duration_days = fields.Float(
        "Durée (j)", readonly=True, digits=(16, 2),
        help="Durée ramenée en journées de travail (heures normales par jour).")
    miro_labor_cost = fields.Monetary(
        "Coût main-d'œuvre", readonly=True, currency_field='currency_id',
        help="Durée × coût horaire chargé de l'équipe.")
    miro_min_lag_days = fields.Float(
        related='phase_template_line_id.min_lag_days', string="Délai technique (j)")

    def _miro_refresh_labor(self, force=False):
        """Recalcule équipe, effectif, durée et coût des phases non commencées
        (toutes si `force`), puis leurs heures prévues."""
        Rate = self.env['miro.crew.rate']
        for task in self.filtered(lambda t: t.construction_element_id and t.phase_template_line_id):
            started = task.x_avancement_global or task.state in ('1_done', '1_canceled')
            if started and not force:
                continue
            element = task.construction_element_id
            line = task.phase_template_line_id
            rate = Rate._rate_for(line.phase_type, element.element_type_id)
            qty = getattr(element, 'qty_%s' % line.qty_key, 0.0) if line.qty_key else 0.0
            hpd = task.company_id.miro_hours_per_day or 8.0
            if rate and qty:
                hours = qty / rate.rate
                vals = {
                    'miro_crew_rate_id': rate.id, 'miro_crew_id': rate.crew_id.id,
                    'miro_headcount': rate.headcount,
                    'miro_duration_hours': hours, 'miro_duration_days': hours / hpd,
                    'miro_labor_cost': hours * rate.crew_hourly_cost,
                    'allocated_hours': hours * rate.headcount,
                }
            else:
                # Cadence connue mais métré nul (hauteur manquante...) : l'équipe
                # est retenue, la durée attend le métré.
                vals = {'miro_crew_rate_id': rate.id or False, 'miro_crew_id': rate.crew_id.id or False,
                        'miro_headcount': rate.headcount if rate else 0,
                        'miro_duration_hours': 0.0, 'miro_duration_days': 0.0,
                        'miro_labor_cost': 0.0}
            task.write(vals)

    def action_miro_refresh_labor(self):
        self._miro_refresh_labor(force=True)
        return True


class ConstructionElement(models.Model):
    _inherit = 'construction.element'

    def write(self, vals):
        res = super().write(vals)
        if set(QTY_FIELDS) & set(vals):
            self.task_ids._miro_refresh_labor()
        return res

    def _generate_tasks(self):
        tasks = super()._generate_tasks()
        tasks._miro_refresh_labor()
        return tasks
