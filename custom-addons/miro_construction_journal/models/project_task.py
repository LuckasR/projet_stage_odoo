from markupsafe import Markup

from odoo import _, api, fields, models

from .site_journal import STATUS_PROGRESS

QTY_FIELDS = ('qty_beton_m3', 'qty_acier_kg', 'qty_coffrage_m2', 'qty_surface_m2')

# Écart (en points) entre l'avancement et la matière ou les heures au-delà
# duquel une phase est à vérifier
CHECK_TOLERANCE = 25.0


class ProjectTask(models.Model):
    """Avancement et coût réel d'une tâche, calculés et jamais saisis.

    Avancement d'une phase : le réalisé cumulé des journaux validés divisé
    par son métré, ou l'état déclaré pour une phase sans métré. Une tâche
    mère est la moyenne de ses filles pondérée par leur coût prévu : une
    dalle à 1 000 000 pèse cent fois plus qu'une implantation à 10 000. La
    matière, les heures et les phases précédentes ne changent pas
    l'avancement : elles le contrôlent.

    Coût réel : journaux validés pour la main-d'œuvre, le matériel et les
    dépenses ; sorties de stock pour les matières. Une tâche mère cumule ses
    sous-tâches."""
    _inherit = 'project.task'

    miro_journal_work_ids = fields.One2many('miro.site.journal.work', 'task_id')
    miro_journal_labor_ids = fields.One2many('miro.site.journal.labor', 'task_id')
    miro_journal_equipment_ids = fields.One2many('miro.site.journal.equipment', 'task_id')
    miro_journal_expense_ids = fields.One2many('miro.site.journal.expense', 'task_id')

    x_cout_mo_reel = fields.Monetary(
        "Main-d'œuvre réelle", compute='_compute_cout_reel_details', store=True,
        currency_field='currency_id')
    x_cout_matiere_reel = fields.Monetary(
        "Matières réelles", compute='_compute_cout_reel_details', store=True,
        currency_field='currency_id')
    x_cout_materiel_reel = fields.Monetary(
        "Matériel réel", compute='_compute_cout_reel_details', store=True,
        currency_field='currency_id')
    x_cout_divers_reel = fields.Monetary(
        "Frais divers réels", compute='_compute_cout_reel_details', store=True,
        currency_field='currency_id')
    x_cout_reel = fields.Monetary(
        compute='_compute_cout_reel', store=True, readonly=True, recursive=True,
        help="Main-d'œuvre, matières, matériel et frais divers de la tâche, "
             "plus ceux de ses sous-tâches. Calculé depuis les journaux de "
             "chantier validés et les consommations.")

    # --- Avancement -------------------------------------------------------
    x_avancement_manuel = fields.Float(
        string="Avancement de la phase (%)", compute='_compute_avancement_journal',
        store=True, readonly=True,
        help="Réalisé cumulé des journaux de chantier validés / métré de la "
             "phase ; pour une phase sans métré : pas commencé 0 %, en cours "
             "50 %, fini 100 %.")
    x_qty_realisee = fields.Float(
        "Réalisé cumulé", compute='_compute_avancement_journal', store=True, digits=(16, 3))
    x_poids_avancement = fields.Monetary(
        "Poids dans l'avancement", compute='_compute_poids_avancement', store=True,
        recursive=True, currency_field='currency_id',
        help="Coût prévu de la phase (main-d'œuvre + matières), ou de toutes les "
             "phases d'une tâche mère : son poids dans l'avancement de l'ouvrage "
             "et du chantier.")
    x_heures_reelles = fields.Float(
        "Heures réalisées", compute='_compute_heures_reelles', store=True,
        help="Heures des ouvriers déclarées sur la phase dans les journaux validés.")
    x_avancement_confiance = fields.Selection([
        ('none', "Pas commencée"),
        ('ok', "Cohérent"),
        ('check', "À vérifier"),
    ], string="Contrôle de l'avancement", compute='_compute_controle_avancement')
    x_controle_avancement = fields.Html(
        "Contrôles", compute='_compute_controle_avancement', sanitize=False)

    @api.depends('miro_journal_work_ids.state', 'miro_journal_work_ids.qty_done',
                 'miro_journal_work_ids.status', 'phase_template_line_id.qty_key',
                 *('construction_element_id.%s' % f for f in QTY_FIELDS))
    def _compute_avancement_journal(self):
        for task in self:
            works = task.miro_journal_work_ids.filtered(lambda w: w.state == 'validated')
            task.x_qty_realisee = sum(works.mapped('qty_done'))
            if task.phase_qty:
                task.x_avancement_manuel = min(max(
                    100.0 * task.x_qty_realisee / task.phase_qty, 0.0), 100.0)
            elif works:
                last = works.sorted(lambda w: (w.date, w.id))[-1]
                task.x_avancement_manuel = STATUS_PROGRESS.get(last.status, 0.0)
            else:
                task.x_avancement_manuel = 0.0

    @api.depends('miro_labor_cost', 'material_need_ids.planned_cost',
                 'child_ids.x_poids_avancement')
    def _compute_poids_avancement(self):
        for task in self:
            if task.child_ids:
                task.x_poids_avancement = sum(task.child_ids.mapped('x_poids_avancement'))
            else:
                task.x_poids_avancement = (task.miro_labor_cost
                                           + sum(task.material_need_ids.mapped('planned_cost')))

    @api.depends('child_ids.x_avancement_global', 'child_ids.x_poids_avancement',
                 'child_ids', 'x_avancement_manuel')
    def _compute_avancement_global(self):
        for task in self:
            if task.child_ids:
                task.x_avancement_global = self._weighted_progress(task.child_ids)
            else:
                task.x_avancement_global = task.x_avancement_manuel

    @api.model
    def _weighted_progress(self, tasks):
        """Moyenne des avancements pondérée par le coût prévu. Une tâche sans
        coût prévu (ni cadence ni matière) ne pèse rien ; si aucune n'en a,
        moyenne simple."""
        if not tasks:
            return 0.0
        total = sum(tasks.mapped('x_poids_avancement'))
        if total:
            return sum(t.x_poids_avancement * t.x_avancement_global for t in tasks) / total
        return sum(tasks.mapped('x_avancement_global')) / len(tasks)

    @api.depends('miro_journal_labor_ids.hours', 'miro_journal_labor_ids.state')
    def _compute_heures_reelles(self):
        for task in self:
            task.x_heures_reelles = sum(task.miro_journal_labor_ids.filtered(
                lambda l: l.state == 'validated').mapped('hours'))

    def _compute_controle_avancement(self):
        for task in self:
            if task.child_ids:
                task.x_avancement_confiance = False
                task.x_controle_avancement = False
                continue
            if not task.x_avancement_manuel and not task.x_heures_reelles:
                task.x_avancement_confiance = 'none'
                task.x_controle_avancement = False
                continue
            alerts = task._progress_checks()
            task.x_avancement_confiance = 'check' if alerts else 'ok'
            task.x_controle_avancement = task._progress_checks_html(alerts)

    def _material_pct(self, extra=None):
        """Part de la matière de la phase déjà utilisée (%), en comptant
        `extra` ({besoin: quantité}) en plus ; None si la phase n'a pas de
        besoin chiffrable."""
        self.ensure_one()
        extra = extra or {}
        needs = self.material_need_ids.filtered(lambda n: n.product_id and n.product_qty > 0)
        if not needs:
            return None
        ratios = [((n.qty_consumed + extra.get(n, 0.0)) / n.product_qty, n.planned_cost)
                  for n in needs]
        total = sum(cost for _r, cost in ratios)
        if total:
            return 100.0 * sum(r * cost for r, cost in ratios) / total
        return 100.0 * sum(r for r, _c in ratios) / len(ratios)

    def _progress_checks(self, progress=None, extra_hours=0.0, extra_material=None, extra_qty=0.0):
        """Contrôles de cohérence de l'avancement d'une phase. Les `extra_*`
        sont ce qu'apporterait un journal pas encore validé."""
        self.ensure_one()
        progress = self.x_avancement_manuel if progress is None else progress
        alerts = []

        if progress > 0 and 'depend_on_ids' in self._fields:
            for previous in self.depend_on_ids.filtered(lambda t: (t.x_avancement_global or 0) < 100):
                alerts.append(_("La phase précédente « %(name)s » n'est pas finie (%(pct)d %%).")
                              % {'name': previous.name, 'pct': round(previous.x_avancement_global or 0)})

        material = self._material_pct(extra_material)
        if material is not None and max(progress, material) >= 10:
            if progress - material > CHECK_TOLERANCE:
                alerts.append(_("Avancement de %(p)d %% mais seulement %(m)d %% de la matière utilisée : "
                                "réalisé déclaré trop haut, ou consommation oubliée ?")
                              % {'p': round(progress), 'm': round(material)})
            elif material - progress > CHECK_TOLERANCE:
                alerts.append(_("%(m)d %% de la matière déjà utilisée pour %(p)d %% d'avancement : "
                                "surconsommation, ou réalisé oublié ?")
                              % {'p': round(progress), 'm': round(material)})

        hours = self.x_heures_reelles + extra_hours
        if self.allocated_hours and hours:
            hours_pct = 100.0 * hours / self.allocated_hours
            if hours_pct - progress > CHECK_TOLERANCE:
                alerts.append(_("%(h)s h passées (%(hp)d %% des heures prévues) pour %(p)d %% "
                                "d'avancement : l'équipe avance moins vite que prévu.")
                              % {'h': round(hours, 1), 'hp': round(hours_pct), 'p': round(progress)})

        done = self.x_qty_realisee + extra_qty
        if self.phase_qty and done > self.phase_qty * 1.01:
            alerts.append(_("Réalisé cumulé (%(d)s) au-delà du métré de la phase (%(q)s) : "
                            "métré à revoir, ou réalisé déclaré en trop ?")
                          % {'d': round(done, 2), 'q': round(self.phase_qty, 2)})
        return alerts

    @api.model
    def _progress_checks_html(self, alerts):
        if not alerts:
            return Markup('<div class="text-success"><i class="fa fa-check-circle"/> %s</div>') % _(
                "Avancement cohérent avec la matière, les heures et les phases précédentes.")
        items = Markup('').join(Markup('<li>%s</li>') % a for a in alerts)
        return Markup('<div class="alert alert-warning mb-0 py-2"><ul class="mb-0 ps-3">%s</ul></div>') % items

    # --- Coût réel ---------------------------------------------------------
    @api.depends('miro_journal_labor_ids.cost', 'miro_journal_labor_ids.state',
                 'miro_journal_equipment_ids.cost', 'miro_journal_equipment_ids.state',
                 'miro_journal_expense_ids.amount', 'miro_journal_expense_ids.state',
                 'material_need_ids.move_ids.state', 'material_need_ids.move_ids.quantity',
                 'material_need_ids.move_ids.price_unit')
    def _compute_cout_reel_details(self):
        def validated(lines):
            return lines.filtered(lambda l: l.state == 'validated')

        for task in self:
            task.x_cout_mo_reel = sum(validated(task.miro_journal_labor_ids).mapped('cost'))
            task.x_cout_materiel_reel = sum(validated(task.miro_journal_equipment_ids).mapped('cost'))
            task.x_cout_divers_reel = sum(validated(task.miro_journal_expense_ids).mapped('amount'))
            # Sorties de stock vers le chantier (journaux de chantier)
            # Un retour en stock (ligne remise en brouillon) se déduit
            task.x_cout_matiere_reel = sum(
                m._miro_consumed_qty() * (m.price_unit or m.product_id.standard_price)
                for m in task.material_need_ids.move_ids if m.state == 'done')

    @api.depends('x_cout_mo_reel', 'x_cout_matiere_reel', 'x_cout_materiel_reel',
                 'x_cout_divers_reel', 'child_ids.x_cout_reel')
    def _compute_cout_reel(self):
        for task in self:
            task.x_cout_reel = (task.x_cout_mo_reel + task.x_cout_matiere_reel
                                + task.x_cout_materiel_reel + task.x_cout_divers_reel
                                + sum(task.child_ids.mapped('x_cout_reel')))
