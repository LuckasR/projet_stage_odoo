from odoo import _, fields, models
from odoo.tools import format_amount, format_date

GRAVITY_ORDER = {'critique': 0, 'haute': 1, 'moyenne': 2, 'faible': 3}


class ProjectProject(models.Model):
    """Vue d'ensemble de la fiche chantier : tout ce qu'il faut savoir d'un
    chantier, calculé à l'ouverture depuis les tâches, les besoins matériaux,
    la main-d'œuvre prévue et les journaux de chantier."""
    _inherit = 'project.project'

    x_overview_html = fields.Html(
        "Vue d'ensemble", compute='_compute_x_overview_html', sanitize=False)
    x_incident_open_count = fields.Integer(compute='_compute_x_overview_counts')
    x_element_count = fields.Integer(compute='_compute_x_overview_counts')

    def _compute_x_overview_counts(self):
        Incident = self.env['construction.task.incident']
        Element = self.env['construction.element']
        for project in self:
            project.x_incident_open_count = Incident.search_count(
                [('project_id', '=', project.id), ('etat', '!=', 'resolu')]) if project.id else 0
            project.x_element_count = Element.search_count(
                [('project_id', '=', project.id)]) if project.id else 0

    def _compute_x_overview_html(self):
        template = 'miro_construction_overview.project_overview'
        for project in self:
            if not isinstance(project.id, int):
                project.x_overview_html = False
                continue
            project.x_overview_html = self.env['ir.qweb']._render(
                template, project._overview_values())

    # ------------------------------------------------------------------
    # Données de la vue d'ensemble
    # ------------------------------------------------------------------
    def _overview_values(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        currency = self.currency_id or self.env.company.currency_id

        def money(value):
            return format_amount(self.env, value or 0.0, currency)

        def pct(part, whole):
            return 100.0 * part / whole if whole else 0.0

        values = {
            'project': self, 'money': money,
            'date': lambda d: format_date(self.env, d) if d else '—',
            'num': lambda v, d=0: ('{:,.%df}' % d).format(v or 0.0).replace(',', ' '),
            'width': lambda v: '%.1f' % min(max(v or 0.0, 0.0), 100.0),
            'label': lambda rec, name: dict(
                rec._fields[name]._description_selection(self.env)).get(rec[name], ''),
        }
        values.update(self._overview_schedule(today))
        values.update(self._overview_costs(pct))
        values.update(self._overview_activity(today))
        values['ouvrages'] = self._overview_ouvrages()
        values['materials'] = self.get_material_dashboard()
        values['incidents'] = self._overview_incidents()
        values['alerts'] = self._overview_alerts(values)
        return values

    def _overview_schedule(self, today):
        """Délai : avancement réel face à l'avancement attendu, si les travaux
        avançaient au même rythme du début à la fin prévue."""
        start, end = self.x_date_debut_travaux, self.x_date_fin_prevue
        progress = self.x_avancement_global or 0.0
        expected = None
        days_total = days_elapsed = days_left = None
        if start and end and end > start:
            days_total = (end - start).days
            days_elapsed = min(max((today - start).days, 0), days_total)
            days_left = (end - today).days
            expected = 100.0 * days_elapsed / days_total
        return {
            'today': today, 'progress': progress, 'expected': expected,
            'schedule_gap': progress - expected if expected is not None else None,
            'days_total': days_total, 'days_elapsed': days_elapsed, 'days_left': days_left,
        }

    def _overview_costs(self, pct):
        """Prévu (chiffré depuis les métrés) face au réel (journaux et sorties
        de stock), et la dérive : valeur produite = budget x avancement."""
        labor_planned = self.miro_labor_cost
        material_planned = self.material_planned_cost
        planned = labor_planned + material_planned
        real = self.x_cout_reel_total
        reference = self.x_budget_total or planned
        earned = reference * (self.x_avancement_global or 0.0) / 100.0
        cpi = earned / real if real and earned else None
        rows = [
            (_("Main-d'œuvre"), labor_planned, self.x_cout_mo_reel_total),
            (_("Matières"), material_planned, self.x_cout_matiere_reel_total),
            (_("Matériel"), 0.0, self.x_cout_materiel_reel_total),
            (_("Frais divers"), 0.0, self.x_cout_divers_reel_total),
        ]
        return {
            'cost_rows': [{'name': n, 'planned': p, 'real': r, 'ratio': pct(r, p) if p else None}
                          for n, p, r in rows],
            'planned_total': planned, 'real_total': real,
            'budget': self.x_budget_total, 'reference': reference,
            'budget_used': pct(real, reference) if reference else None,
            'earned': earned, 'cpi': cpi,
            # Si la dérive constatée continue jusqu'au bout
            'forecast': reference / cpi if cpi else None,
        }

    def _overview_activity(self, today):
        journals = self.miro_journal_ids
        validated = journals.filtered(lambda j: j.state == 'validated')
        # Les heures comptent dès que leur ligne est validée
        labor = journals.work_ids.labor_line_ids.filtered(lambda l: l.state == 'validated')
        last = validated.sorted('date', reverse=True)[:1]
        return {
            'journals': journals.sorted('date', reverse=True)[:6],
            'journal_count': len(validated),
            'journal_to_validate': len(journals.filtered(lambda j: j.state == 'submitted')),
            'hours_real': sum(labor.mapped('hours')),
            'hours_planned': self.miro_person_hours,
            'avg_headcount': (sum(validated.mapped('headcount')) / len(validated)) if validated else 0.0,
            'last_journal': last,
            'days_since_journal': (today - last.date).days if last else None,
        }

    def _overview_ouvrages(self):
        tasks = self.tasks
        ouvrages = tasks.filtered('is_ouvrage') or tasks.filtered(lambda t: not t.parent_id)
        result = []
        for ouvrage in ouvrages.sorted(lambda t: (t.sequence, t.id)):
            descendants = ouvrage._get_all_descendants()
            phases = descendants.filtered(lambda t: not t.child_ids)
            result.append({
                'task': ouvrage,
                'progress': ouvrage.x_avancement_global or 0.0,
                'phases': len(phases),
                'done': len(phases.filtered(lambda t: (t.x_avancement_global or 0) >= 100)),
                'late': len((descendants | ouvrage).filtered('x_est_en_retard')),
                'real': ouvrage.x_cout_reel,
            })
        return result

    def _overview_incidents(self):
        incidents = self.env['construction.task.incident'].search(
            [('project_id', '=', self.id), ('etat', '!=', 'resolu')])
        return incidents.sorted(lambda i: (GRAVITY_ORDER.get(i.gravite, 9),
                                           -(i.date_incident or fields.Date.today()).toordinal()))

    def _overview_alerts(self, v):
        """Ce qui demande une action, du plus grave au moins grave."""
        alerts = []

        def add(level, text):
            alerts.append({'level': level, 'text': text})

        kpis = v['materials']['kpis']
        critical = v['incidents'].filtered(lambda i: i.gravite in ('critique', 'haute'))
        if v['budget_used'] is not None and v['budget_used'] > 100:
            add('danger', _("Coût réel au-delà du budget : %s dépensés pour %s.")
                % (v['money'](v['real_total']), v['money'](v['reference'])))
        if v['cpi'] is not None and v['cpi'] < 0.95:
            add('danger', _("Dérive des coûts : %d %% de plus que prévu pour l'avancement atteint.")
                % round(100 * (1 / v['cpi'] - 1)))
        if critical:
            add('danger', _("%d incident(s) grave(s) non résolu(s).") % len(critical))
        if v['schedule_gap'] is not None and v['schedule_gap'] < -10:
            add('danger' if v['schedule_gap'] < -25 else 'warning',
                _("Retard sur le planning : %d points d'avancement sous l'attendu à ce jour.")
                % round(-v['schedule_gap']))
        if v['days_left'] is not None and v['days_left'] < 0 and v['progress'] < 100:
            add('danger', _("Date de fin prévue dépassée de %d jour(s).") % -v['days_left'])
        if self.x_task_en_retard_count:
            add('warning', _("%d tâche(s) en retard.") % self.x_task_en_retard_count)
        to_check = self.tasks.filtered(lambda t: not t.child_ids and t.x_avancement_confiance == 'check')
        if to_check:
            add('warning', _("%d phase(s) dont l'avancement est à vérifier (matière, heures ou "
                             "phase précédente incohérentes) : voir la fiche de la phase.")
                % len(to_check))
        if kpis['shortage']:
            add('warning', _("%d matériau(x) en stock insuffisant.") % kpis['shortage'])
        if kpis['overrun']:
            add('warning', _("%d matériau(x) en surconsommation.") % kpis['overrun'])
        if v['journal_to_validate']:
            add('info', _("%d journal(aux) de chantier à valider.") % v['journal_to_validate'])
        if self.x_status == 'en_cours' and (v['days_since_journal'] is None or v['days_since_journal'] > 3):
            add('info', _("Aucun journal validé depuis %s.")
                % (_("le début") if v['days_since_journal'] is None
                   else _("%d jours") % v['days_since_journal']))
        if kpis['no_product']:
            add('info', _("%d besoin(s) matériau sans produit choisi.") % kpis['no_product'])
        if self.miro_phases_without_rate:
            add('info', _("%d phase(s) sans cadence : leur main-d'œuvre n'est pas chiffrée.")
                % self.miro_phases_without_rate)
        if self.miro_phases_without_qty:
            add('info', _("%d phase(s) sans métré : durée et besoins à zéro.")
                % self.miro_phases_without_qty)
        if not self.x_budget_total:
            add('info', _("Aucun budget saisi : les écarts sont mesurés sur le coût prévu chiffré."))
        if not (self.x_date_debut_travaux and self.x_date_fin_prevue):
            add('info', _("Dates de début et de fin des travaux à renseigner pour suivre le délai."))
        return alerts

    # ------------------------------------------------------------------
    # Accès directs
    # ------------------------------------------------------------------
    def action_open_today_journal(self):
        """Le journal du jour : celui qui existe, sinon un nouveau prérempli."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        journal = self.env['miro.site.journal'].search(
            [('project_id', '=', self.id), ('date', '=', today)], limit=1)
        return {
            'type': 'ir.actions.act_window', 'name': _("Journal du jour"),
            'res_model': 'miro.site.journal', 'view_mode': 'form',
            'views': [(False, 'form')], 'res_id': journal.id or False,
            'context': {'default_project_id': self.id, 'default_date': today},
        }

    def action_open_open_incidents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Incidents — %s") % self.name,
            'res_model': 'construction.task.incident', 'view_mode': 'tree,form',
            'views': [(False, 'tree'), (False, 'form')],
            'domain': [('project_id', '=', self.id), ('etat', '!=', 'resolu')],
        }

    def action_open_elements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Éléments — %s") % self.name,
            'res_model': 'construction.element', 'view_mode': 'tree,form',
            'views': [(False, 'tree'), (False, 'form')],
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id, 'search_default_group_ouvrage': 1},
        }
