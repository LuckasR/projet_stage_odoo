from collections import defaultdict

import pytz
from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError

from .planner import SitePlanner


class ProjectTask(models.Model):
    _inherit = 'project.task'

    miro_planned_start = fields.Datetime("Début planifié")
    miro_planned_end = fields.Datetime("Fin planifiée")

    def write(self, vals):
        """Une barre déplacée dans le Gantt (dates planifiées modifiées à la
        main) met à jour les dates prévues et l'échéance de la phase."""
        res = super().write(vals)
        if self.env.context.get('miro_planner') or not (
                {'miro_planned_start', 'miro_planned_end'} & set(vals)):
            return res
        for task in self:
            sync = {}
            local = task.with_context(tz=task.project_id.miro_calendar_id.tz
                                      or task.project_id.resource_calendar_id.tz or 'UTC')
            if task.miro_planned_start:
                sync['x_date_debut_prevue'] = fields.Datetime.context_timestamp(
                    local, task.miro_planned_start).date()
            if task.miro_planned_end:
                sync['x_date_fin_prevue'] = fields.Datetime.context_timestamp(
                    local, task.miro_planned_end).date()
                if task.project_id.miro_update_deadlines:
                    sync['date_deadline'] = task.miro_planned_end
            if sync:
                super(ProjectTask, task.with_context(miro_planner=True)).write(sync)
        return res


class MiroProjectCrewCapacity(models.Model):
    """Nombre d'équipes d'un type pouvant travailler en même temps sur un
    chantier (remplace la valeur générale du chantier)."""
    _name = 'miro.project.crew.capacity'
    _description = "Équipes en parallèle sur un chantier"

    project_id = fields.Many2one('project.project', required=True, ondelete='cascade', index=True)
    crew_id = fields.Many2one('miro.crew', string="Équipe", required=True)
    count = fields.Integer("Équipes en parallèle", default=1, required=True)

    _sql_constraints = [('crew_uniq', 'unique(project_id, crew_id)',
                         "Une seule ligne par équipe et par chantier.")]


class ProjectProject(models.Model):
    _inherit = 'project.project'

    miro_parallel_crews = fields.Integer(
        "Équipes de même type en parallèle", default=1,
        help="Combien d'équipes d'un même type (coffrage, coulage...) le planning "
             "peut faire travailler en même temps. Plus il y en a, plus le chantier "
             "est court et plus l'effectif proposé est élevé.")
    miro_crew_capacity_ids = fields.One2many(
        'miro.project.crew.capacity', 'project_id', string="Équipes en parallèle par type",
        help="Exceptions à la valeur générale : 2 équipes de ferraillage, 1 de coulage...")

    miro_calendar_id = fields.Many2one(
        'resource.calendar', string="Calendrier du chantier",
        help="Heures et jours travaillés du chantier (semaine de 6 jours...). "
             "Vide : le calendrier de la société.")
    miro_update_deadlines = fields.Boolean(
        "Reporter sur les échéances", default=True,
        help="Le planning fixe aussi l'échéance des phases : les retards sont "
             "alors mesurés par rapport au planning.")
    miro_planned_on = fields.Datetime("Planifié le", readonly=True)
    miro_planning_warnings = fields.Text("Remarques du planning", readonly=True)
    miro_planned_phase_count = fields.Integer("Phases planifiées", readonly=True)
    miro_planned_workdays = fields.Float("Durée (jours ouvrés)", readonly=True, digits=(16, 1))
    miro_load_ids = fields.One2many('miro.planning.load', 'project_id', string="Charge par métier")
    miro_load_summary = fields.Html("Charge par métier", compute='_compute_miro_load_summary',
                                    sanitize=False)

    # ------------------------------------------------------------------
    def action_miro_plan(self):
        """Planifie les phases du chantier à partir de la date de début des
        travaux, puis enregistre dates, échéances et charge par métier."""
        self.ensure_one()
        if not self.x_date_debut_travaux:
            raise UserError(_("Renseignez la date de début des travaux du chantier : "
                              "le planning part de cette date."))
        phases = self.env['project.task'].search([
            ('project_id', '=', self.id), ('construction_element_id', '!=', False)])
        # Durées et équipes à jour avant de planifier
        phases._miro_refresh_labor()
        planner = SitePlanner(self, self.x_date_debut_travaux)
        result = planner.run()
        self._miro_apply_plan(planner, result)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("Planning du chantier"),
                'type': 'warning' if planner.warnings else 'success', 'sticky': bool(planner.warnings),
                'message': _("%(n)d phase(s) planifiée(s) : fin prévue le %(end)s.%(warn)s") % {
                    'n': len(result),
                    'end': self.x_date_fin_prevue and self.x_date_fin_prevue.strftime('%d/%m/%Y') or '—',
                    'warn': (" " + _("%d remarque(s) : voir l'onglet Planning.") % len(planner.warnings))
                            if planner.warnings else ""},
                # Recharge la fiche : dates et charge à jour
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _miro_apply_plan(self, planner, result):
        utc = pytz.utc
        tz = planner.work.tz
        hpd = planner.hours_per_day

        def naive(moment):
            return moment.astimezone(utc).replace(tzinfo=None)

        for task, (start, end) in result.items():
            hours = (task.miro_duration_hours or 0.0) * (1 - min(task.x_avancement_global or 0.0, 100.0) / 100.0)
            vals = {
                'miro_planned_start': naive(start), 'miro_planned_end': naive(end),
                'x_date_debut_prevue': start.astimezone(tz).date(),
                'x_date_fin_prevue': end.astimezone(tz).date(),
                'x_duree_prevue_jours': round(hours / hpd, 2),
            }
            if self.miro_update_deadlines:
                vals['date_deadline'] = naive(end)
            task.with_context(miro_planner=True).write(vals)

        # Ouvrages : de la première à la dernière de leurs phases
        by_parent = defaultdict(list)
        for task, span in result.items():
            if task.parent_id:
                by_parent[task.parent_id].append(span)
        for parent, spans in by_parent.items():
            start, end = min(s for s, _e in spans), max(e for _s, e in spans)
            vals = {'miro_planned_start': naive(start), 'miro_planned_end': naive(end),
                    'x_date_debut_prevue': start.astimezone(tz).date(),
                    'x_date_fin_prevue': end.astimezone(tz).date()}
            if self.miro_update_deadlines:
                vals['date_deadline'] = naive(end)
            parent.with_context(miro_planner=True).write(vals)

        # Charge par métier : l'effectif proposé d'un métier est la pointe de
        # tout le planning ; chaque jour est comparé à cette pointe.
        self.miro_load_ids.unlink()
        daily = planner.daily_load()
        proposed = defaultdict(int)
        for (day, trade), (peak, hours) in daily.items():
            proposed[trade] = max(proposed[trade], peak)
        self.env['miro.planning.load'].create([{
            'project_id': self.id, 'date': day, 'trade_id': trade.id,
            'needed': peak, 'available': proposed[trade], 'person_hours': hours,
            'usage_pct': 100.0 * peak / proposed[trade] if proposed[trade] else 0.0,
            'saturated': peak >= proposed[trade],
        } for (day, trade), (peak, hours) in daily.items()])
        for trade in proposed:
            if not trade.hourly_cost:
                planner._warn(_("Coût horaire inconnu pour « %s » : saisissez son coût "
                                "de référence (Configuration > Métiers), sinon sa "
                                "main-d'œuvre est chiffrée à 0.") % trade.name)

        end = max((e for _s, e in result.values()), default=None)
        workdays = 0.0
        if end:
            data = planner.work.calendar.get_work_duration_data(planner.work.start, end, compute_leaves=True)
            workdays = data.get('days', 0.0)
        self.write({
            'x_date_fin_prevue': end.astimezone(tz).date() if end else self.x_date_fin_prevue,
            'miro_planned_on': fields.Datetime.now(),
            'miro_planning_warnings': "\n".join(planner.warnings) or False,
            'miro_planned_phase_count': len(result),
            'miro_planned_workdays': workdays,
        })

    # ------------------------------------------------------------------
    def _compute_miro_load_summary(self):
        for project in self:
            loads = project.miro_load_ids
            if not loads:
                project.miro_load_summary = Markup('<p class="text-muted">%s</p>') % _(
                    "Pas encore de planning : renseignez la date de début des travaux "
                    "puis cliquez sur « Planifier le chantier ».")
                continue
            stats = defaultdict(lambda: {'days': 0, 'peak': 0, 'hours': 0.0})
            for load in loads:
                s = stats[load.trade_id]
                s['days'] += 1
                s['peak'] = max(s['peak'], load.needed)
                s['hours'] += load.person_hours
            hpd = project.company_id.miro_hours_per_day or 8.0
            rows = Markup('')
            for trade, s in sorted(stats.items(), key=lambda kv: -kv[1]['hours']):
                current = trade.sudo().employee_count
                missing = max(s['peak'] - current, 0)
                rows += Markup(
                    '<tr><td>%s</td><td class="text-end fw-bold">%s</td><td class="text-end">%.1f</td>'
                    '<td class="text-end">%s</td><td class="text-end">%.1f</td>'
                    '<td class="text-end text-muted">%s</td><td class="text-end %s">%s</td></tr>') % (
                    trade.name, s['peak'], s['hours'] / hpd / s['days'] if s['days'] else 0.0,
                    s['days'], s['hours'], current,
                    'text-warning fw-bold' if missing else 'text-success', missing or "—")
            project.miro_load_summary = Markup(
                '<p class="text-muted">%s</p>'
                '<table class="table table-sm"><thead><tr><th>%s</th><th class="text-end">%s</th>'
                '<th class="text-end">%s</th><th class="text-end">%s</th><th class="text-end">%s</th>'
                '<th class="text-end">%s</th><th class="text-end">%s</th></tr></thead>'
                '<tbody>%s</tbody></table>') % (
                _("Proposition du système : effectif à prévoir pour tenir ce planning. Les "
                  "ouvriers sont affectés par le chef de chantier au démarrage des travaux."),
                _("Métier"), _("Effectif à prévoir (pointe)"), _("Effectif moyen"),
                _("Jours de travail"), _("Heures-personnes"), _("Employés actuels"),
                _("À recruter / affecter"), rows)

    def action_miro_view_load(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Charge par métier — %s") % self.name,
            'res_model': 'miro.planning.load', 'view_mode': 'graph,pivot,tree',
            'domain': [('project_id', '=', self.id)],
            'context': {'graph_groupbys': ['date:week', 'trade_id'], 'pivot_row_groupby': ['trade_id'],
                        'pivot_column_groupby': ['date:week']},
        }

    def action_miro_view_schedule(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Planning — %s") % self.name,
            'res_model': 'project.task',
            'view_mode': 'miro_gantt,calendar,tree,form',
            'views': [(self.env.ref('miro_construction_planning.view_task_planning_gantt').id, 'miro_gantt'),
                      (self.env.ref('miro_construction_planning.view_task_planning_calendar').id, 'calendar'),
                      (self.env.ref('miro_construction_planning.view_task_planning_tree').id, 'tree'),
                      (False, 'form')],
            'domain': [('project_id', '=', self.id), ('construction_element_id', '!=', False),
                       ('miro_planned_start', '!=', False)],
            'limit': 2000,
            'context': {
                # Calendrier et Gantt s'ouvrent sur le début du chantier
                'initial_date': self.x_date_debut_travaux and str(self.x_date_debut_travaux),
                'miro_gantt_initial_date': self.x_date_debut_travaux and str(self.x_date_debut_travaux),
                # Toutes les phases d'un coup : une page de 81 couperait les
                # éléments (une seule de leurs phases affichée)
                'miro_gantt_limit': 2000,
            },
        }
