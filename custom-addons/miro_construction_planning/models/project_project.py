from collections import defaultdict

from markupsafe import Markup, escape

from odoo import _, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    miro_daily_overhead = fields.Monetary(
        "Frais fixes de chantier par jour", currency_field='currency_id',
        help="Gardiennage, location de matériel, encadrement... : ce que coûte "
             "chaque jour de chantier, quel que soit le travail fait. C'est lui "
             "qui départage, au planning, une équipe renforcée (plus chère, plus "
             "rapide) d'une petite équipe.")
    miro_labor_cost = fields.Monetary(
        "Coût main-d'œuvre prévu", compute='_compute_miro_labor', currency_field='currency_id')
    miro_person_hours = fields.Float("Heures-personnes prévues", compute='_compute_miro_labor')
    miro_crew_days = fields.Float(
        "Journées d'équipe", compute='_compute_miro_labor',
        help="Somme des durées des phases, en journées (sans parallélisme).")
    miro_phases_without_rate = fields.Integer(
        "Phases sans cadence", compute='_compute_miro_labor',
        help="Phases dont le type n'a aucune cadence d'équipe : ni durée, ni coût.")
    miro_phases_without_qty = fields.Integer(
        "Phases sans métré", compute='_compute_miro_labor',
        help="Phases qui ont une cadence mais un métré nul (hauteur ou épaisseur "
             "manquante sur l'élément) : leur durée reste à zéro.")
    miro_labor_summary = fields.Html("Main-d'œuvre par métier", compute='_compute_miro_labor',
                                     sanitize=False)

    def _compute_miro_labor(self):
        for project in self:
            phases = self.env['project.task'].search([
                ('project_id', '=', project.id), ('construction_element_id', '!=', False),
                ('phase_template_line_id', '!=', False)])
            project.miro_labor_cost = sum(phases.mapped('miro_labor_cost'))
            project.miro_person_hours = sum(p.miro_duration_hours * p.miro_headcount for p in phases)
            project.miro_crew_days = sum(phases.mapped('miro_duration_days'))
            project.miro_phases_without_rate = len(phases.filtered(lambda p: not p.miro_crew_rate_id))
            project.miro_phases_without_qty = len(phases.filtered(
                lambda p: p.miro_crew_rate_id and not p.miro_duration_hours))
            project.miro_labor_summary = project._miro_labor_table(phases)

    def _miro_labor_table(self, phases):
        """Heures-personnes et coût par métier, d'après la composition des
        équipes retenues."""
        by_trade = defaultdict(lambda: [0.0, 0.0])
        for phase in phases.filtered('miro_crew_id'):
            for line in phase.miro_crew_id.line_ids:
                hours = phase.miro_duration_hours * line.quantity
                by_trade[line.trade_id][0] += hours
                by_trade[line.trade_id][1] += hours * line.trade_id.hourly_cost
        if not by_trade:
            return Markup('<p class="text-muted">%s</p>') % _(
                "Aucune phase chiffrée : définissez les cadences des équipes "
                "(Construction > Configuration > Cadences).")
        currency = self.currency_id
        rows = Markup('').join(
            Markup('<tr><td>%s</td><td class="text-end">%s</td><td class="text-end">%s</td>'
                   '<td class="text-end">%s</td><td class="text-end">%s</td></tr>') % (
                trade.name, trade.employee_count, "%.1f" % hours, "%.1f" % (hours / 8.0),
                currency.format(cost) if currency else "%.0f" % cost)
            for trade, (hours, cost) in sorted(by_trade.items(), key=lambda kv: -kv[1][1]))
        return Markup(
            '<table class="table table-sm o_miro_labor_table"><thead><tr>'
            '<th>%s</th><th class="text-end">%s</th><th class="text-end">%s</th>'
            '<th class="text-end">%s</th><th class="text-end">%s</th></tr></thead>'
            '<tbody>%s</tbody></table>') % (
            _("Métier"), _("Employés actuels"), _("Heures-personnes"),
            _("Journées (8 h)"), _("Coût"), rows)

    def action_miro_refresh_labor(self):
        self.ensure_one()
        phases = self.env['project.task'].search([
            ('project_id', '=', self.id), ('construction_element_id', '!=', False)])
        phases._miro_refresh_labor()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _("Main-d'œuvre"), 'type': 'success', 'sticky': False,
                       'message': _("%d phase(s) recalculée(s) ; les phases commencées "
                                    "gardent leurs valeurs.") % len(phases)},
        }
