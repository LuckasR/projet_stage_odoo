from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date


class MiroSiteJournal(models.Model):
    """Journal de chantier : la journée d'un chantier, déclarée par le chef
    de chantier. Il regroupe les travaux du jour, un par phase, chacun avec
    sa main-d'œuvre, sa consommation, son matériel et ses dépenses. À la
    validation (conducteur de travaux) il est figé : les matières sortent du
    stock, l'avancement des phases est mis à jour, et ses lignes comptent
    dans le coût réel."""
    _name = 'miro.site.journal'
    _description = "Journal de chantier"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char("Journal", compute='_compute_name', store=True)
    project_id = fields.Many2one(
        'project.project', string="Chantier", required=True, index=True, tracking=True)
    date = fields.Date("Date", required=True, default=fields.Date.context_today, tracking=True)
    user_id = fields.Many2one(
        'res.users', string="Chef de chantier", default=lambda self: self.env.user, tracking=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('draft', "Brouillon"),
        ('submitted', "Soumis"),
        ('validated', "Validé"),
    ], string="État", default='draft', required=True, tracking=True, index=True)
    validated_by_id = fields.Many2one('res.users', string="Validé par", readonly=True)
    validated_on = fields.Datetime("Validé le", readonly=True)

    location_id = fields.Many2one(
        'stock.location', string="Matières prises dans", required=True,
        domain=[('usage', '=', 'internal')],
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1).lot_stock_id)

    weather = fields.Selection([
        ('sunny', "Ensoleillé"),
        ('cloudy', "Nuageux"),
        ('rain', "Pluie"),
        ('storm', "Intempérie (arrêt)"),
    ], string="Météo")
    hours_lost = fields.Float(
        "Heures perdues", help="Heures de chantier arrêtées (intempéries, "
                               "attente de livraison, panne...).")
    notes = fields.Html("Incidents et observations")

    work_ids = fields.One2many('miro.site.journal.work', 'journal_id', string="Travaux du jour")
    # Les frais sans phase se saisissent à part (gardiennage, engin qui sert
    # tout le chantier...) ; ceux d'une phase sont dans son travail.
    site_equipment_line_ids = fields.One2many(
        'miro.site.journal.equipment', 'journal_id', string="Matériel du chantier",
        domain=[('work_id', '=', False)])
    site_expense_line_ids = fields.One2many(
        'miro.site.journal.expense', 'journal_id', string="Dépenses du chantier",
        domain=[('work_id', '=', False)])

    headcount = fields.Integer("Ouvriers présents", compute='_compute_totals', store=True)
    labor_hours = fields.Float("Heures travaillées", compute='_compute_totals', store=True)
    labor_cost = fields.Monetary("Main-d'œuvre", compute='_compute_totals', store=True)
    material_cost = fields.Monetary("Matières", compute='_compute_totals', store=True)
    equipment_cost = fields.Monetary("Matériel", compute='_compute_totals', store=True)
    expense_cost = fields.Monetary("Dépenses", compute='_compute_totals', store=True)
    total_cost = fields.Monetary("Coût de la journée", compute='_compute_totals', store=True)

    _sql_constraints = [
        ('project_date_uniq', 'unique(project_id, date)',
         "Il existe déjà un journal pour ce chantier à cette date."),
    ]

    @api.depends('project_id.name', 'date')
    def _compute_name(self):
        for journal in self:
            journal.name = _("Journal du %(date)s — %(project)s") % {
                'date': format_date(self.env, journal.date) if journal.date else '',
                'project': journal.project_id.name or ''}

    @api.depends('work_ids.labor_line_ids.employee_id', 'work_ids.labor_line_ids.hours',
                 'work_ids.labor_line_ids.cost', 'work_ids.material_line_ids.cost',
                 'work_ids.equipment_line_ids.cost', 'work_ids.expense_line_ids.amount',
                 'site_equipment_line_ids.cost', 'site_expense_line_ids.amount')
    def _compute_totals(self):
        for journal in self:
            labor = journal.work_ids.labor_line_ids
            journal.headcount = len(labor.employee_id)
            journal.labor_hours = sum(labor.mapped('hours'))
            journal.labor_cost = sum(labor.mapped('cost'))
            journal.material_cost = sum(journal.work_ids.material_line_ids.mapped('cost'))
            journal.equipment_cost = sum((journal.work_ids.equipment_line_ids
                                          | journal.site_equipment_line_ids).mapped('cost'))
            journal.expense_cost = sum((journal.work_ids.expense_line_ids
                                        | journal.site_expense_line_ids).mapped('amount'))
            journal.total_cost = (journal.labor_cost + journal.material_cost
                                  + journal.equipment_cost + journal.expense_cost)

    # ------------------------------------------------------------------
    # Verrou : un journal validé ne bouge plus
    # ------------------------------------------------------------------
    _LOCK_FREE = {'message_main_attachment_id', 'activity_ids'}

    def write(self, vals):
        if set(vals) - self._LOCK_FREE and self.filtered(lambda j: j.state == 'validated') \
                and not self.env.context.get('miro_journal_unlocked'):
            raise UserError(_("Un journal validé ne peut plus être modifié."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda j: j.state == 'validated'):
            raise UserError(_("Un journal validé ne peut pas être supprimé."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _check_state(self, *states):
        if self.filtered(lambda j: j.state not in states):
            raise UserError(_("Cette action n'est pas possible dans l'état actuel du journal."))

    def _check_not_empty(self):
        for journal in self:
            if not (journal.work_ids or journal.site_equipment_line_ids
                    or journal.site_expense_line_ids or journal.hours_lost):
                raise UserError(_("Le journal du %s est vide.") % format_date(self.env, journal.date))

    def action_submit(self):
        self._check_state('draft')
        self._check_not_empty()
        self.write({'state': 'submitted'})

    def action_back_to_draft(self):
        self._check_state('submitted')
        self.write({'state': 'draft'})

    def action_validate(self):
        """Fige le journal : sortie de stock des matières, avancement des
        phases. Les coûts réels se recalculent d'eux-mêmes."""
        self._check_state('draft', 'submitted')
        self._check_not_empty()
        for journal in self.sorted('date'):
            per_need = defaultdict(float)
            for line in journal.work_ids.material_line_ids:
                per_need[line.need_id] += line.quantity
            self.env['construction.material.need']._consume(
                per_need, journal.location_id, origin=journal.name)
            # Avancement calculé AVANT de passer validé : le cumul antérieur
            # ne compte que les journaux déjà validés.
            reached = {work.task_id: work.progress_after for work in journal.work_ids}
            journal.with_context(miro_journal_unlocked=True).write({
                'state': 'validated', 'validated_by_id': self.env.uid,
                'validated_on': fields.Datetime.now()})
            for task, progress in reached.items():
                if progress > task.x_avancement_manuel:
                    task.x_avancement_manuel = round(progress, 1)
        return True

    def action_copy_previous_team(self):
        """Reprend les travaux du dernier journal du chantier (phases, équipe,
        matériel) : le chef de chantier n'a plus qu'à saisir les quantités et
        corriger les écarts du jour. Les phases terminées ne sont pas reprises."""
        self.ensure_one()
        self._check_state('draft')
        previous = self.search([('project_id', '=', self.project_id.id),
                                ('date', '<', self.date)], order='date desc', limit=1)
        if not previous:
            raise UserError(_("Aucun journal antérieur sur ce chantier."))
        known = self.work_ids.task_id
        Work = self.env['miro.site.journal.work']
        for old in previous.work_ids:
            if old.task_id in known or old.task_id.x_avancement_global >= 100:
                continue
            Work.create({
                'journal_id': self.id, 'task_id': old.task_id.id,
                'material_line_ids': Work._material_commands(old.task_id),
                'labor_line_ids': [Command.create({
                    'employee_id': l.employee_id.id, 'hours': l.hours}) for l in old.labor_line_ids],
                'equipment_line_ids': [Command.create({
                    'equipment_id': l.equipment_id.id, 'hours': l.hours}) for l in old.equipment_line_ids],
            })
        return True


class MiroSiteJournalWork(models.Model):
    """Travail du jour sur une phase : ce qui a été réalisé (quantité dans
    l'unité de la phase, ou % pour une phase sans métré), et ce que ça a
    demandé — ouvriers, matières de la phase, matériel, dépenses."""
    _name = 'miro.site.journal.work'
    _description = "Travail du journal de chantier"
    _order = 'journal_id, sequence, id'
    _rec_name = 'task_id'

    journal_id = fields.Many2one('miro.site.journal', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    project_id = fields.Many2one(related='journal_id.project_id', store=True, string="Chantier")
    date = fields.Date(related='journal_id.date', store=True)
    state = fields.Selection(related='journal_id.state', store=True, string="État")
    currency_id = fields.Many2one(related='journal_id.currency_id')
    task_id = fields.Many2one(
        'project.task', string="Phase", required=True, index=True,
        domain="[('project_id', '=', project_id), ('child_ids', '=', False)]")
    element_id = fields.Many2one(related='task_id.construction_element_id', string="Élément")

    # --- Réalisé ----------------------------------------------------------
    phase_qty = fields.Float(related='task_id.phase_qty', string="Métré de la phase")
    phase_qty_label = fields.Char(related='task_id.phase_qty_label', string="Unité")
    qty_before = fields.Float(
        "Déjà réalisé", compute='_compute_progress', digits=(16, 3),
        help="Cumul des journaux validés avant celui-ci.")
    qty_done = fields.Float("Réalisé ce jour", digits=(16, 3))
    progress_pct = fields.Float(
        "Avancement atteint (%)",
        help="Pour une phase sans métré : avancement atteint à la fin de la journée.")
    progress_after = fields.Float("Avancement après (%)", compute='_compute_progress')
    note = fields.Char("Remarque")

    # --- Ce que le travail a demandé ---------------------------------------
    labor_line_ids = fields.One2many('miro.site.journal.labor', 'work_id', string="Main-d'œuvre")
    material_line_ids = fields.One2many('miro.site.journal.material', 'work_id', string="Consommation")
    equipment_line_ids = fields.One2many('miro.site.journal.equipment', 'work_id', string="Matériel")
    expense_line_ids = fields.One2many('miro.site.journal.expense', 'work_id', string="Dépenses")

    headcount = fields.Integer("Ouvriers", compute='_compute_totals', store=True)
    labor_hours = fields.Float("Heures", compute='_compute_totals', store=True)
    total_cost = fields.Monetary("Coût", compute='_compute_totals', store=True)

    _sql_constraints = [
        ('journal_task_uniq', 'unique(journal_id, task_id)',
         "Une phase ne figure qu'une fois par journal : regroupez ses travaux."),
    ]

    @api.depends('task_id', 'qty_done', 'progress_pct', 'date')
    def _compute_progress(self):
        Work = self.env['miro.site.journal.work']
        for work in self:
            before = Work.search([
                ('task_id', '=', work.task_id.id), ('state', '=', 'validated'),
                ('id', '!=', work._origin.id or 0)]) if work.task_id else Work
            work.qty_before = sum(before.mapped('qty_done'))
            if work.phase_qty:
                work.progress_after = min(
                    100.0, 100.0 * (work.qty_before + work.qty_done) / work.phase_qty)
            else:
                work.progress_after = min(max(work.progress_pct, 0.0), 100.0)

    @api.depends('labor_line_ids.employee_id', 'labor_line_ids.hours', 'labor_line_ids.cost',
                 'material_line_ids.cost', 'equipment_line_ids.cost', 'expense_line_ids.amount')
    def _compute_totals(self):
        for work in self:
            work.headcount = len(work.labor_line_ids.employee_id)
            work.labor_hours = sum(work.labor_line_ids.mapped('hours'))
            work.total_cost = (sum(work.labor_line_ids.mapped('cost'))
                               + sum(work.material_line_ids.mapped('cost'))
                               + sum(work.equipment_line_ids.mapped('cost'))
                               + sum(work.expense_line_ids.mapped('amount')))

    @api.model
    def _material_commands(self, task):
        """Une ligne de consommation par besoin de la phase : le chef de
        chantier n'a qu'à corriger les quantités."""
        return [Command.create({'need_id': need.id, 'quantity': 0.0})
                for need in task.material_need_ids.filtered('product_id')]

    @api.onchange('task_id')
    def _onchange_task_id(self):
        self.material_line_ids = [Command.clear()] + self._material_commands(self.task_id)
        self._onchange_qty_done()

    @api.onchange('qty_done')
    def _onchange_qty_done(self):
        """Propose la consommation théorique de la quantité réalisée."""
        for line in self.material_line_ids:
            line.quantity = line.planned_qty

    @api.constrains('qty_done', 'progress_pct')
    def _check_values(self):
        for work in self:
            if work.qty_done < 0 or not 0 <= work.progress_pct <= 100:
                raise ValidationError(_("Quantité réalisée ou avancement invalide sur %s.")
                                      % work.task_id.display_name)

    def _check_unlocked(self):
        if self.env.context.get('miro_journal_unlocked'):
            return
        if self.journal_id.filtered(lambda j: j.state == 'validated'):
            raise UserError(_("Un journal validé ne peut plus être modifié."))

    @api.model_create_multi
    def create(self, vals_list):
        works = super().create(vals_list)
        works._check_unlocked()
        return works

    def write(self, vals):
        self._check_unlocked()
        return super().write(vals)

    def unlink(self):
        self._check_unlocked()
        return super().unlink()


class MiroSiteJournalLine(models.AbstractModel):
    """Ce que toutes les lignes d'un journal ont en commun : rattachées à un
    travail (donc à sa phase) ou, pour le matériel et les dépenses, au
    chantier entier ; et le verrou des journaux validés."""
    _name = 'miro.site.journal.line'
    _description = "Ligne de journal de chantier"

    work_id = fields.Many2one('miro.site.journal.work', string="Travail", ondelete='cascade', index=True)
    journal_id = fields.Many2one(
        'miro.site.journal', compute='_compute_journal_id', store=True, readonly=False,
        precompute=True, required=True, ondelete='cascade', index=True)
    task_id = fields.Many2one(related='work_id.task_id', store=True, string="Phase", index=True)
    project_id = fields.Many2one(related='journal_id.project_id', store=True, string="Chantier")
    date = fields.Date(related='journal_id.date', store=True)
    state = fields.Selection(related='journal_id.state', store=True, string="État")
    currency_id = fields.Many2one(related='journal_id.currency_id')

    @api.depends('work_id')
    def _compute_journal_id(self):
        for line in self.filtered('work_id'):
            line.journal_id = line.work_id.journal_id

    def _check_unlocked(self):
        if self.env.context.get('miro_journal_unlocked'):
            return
        if self.journal_id.filtered(lambda j: j.state == 'validated'):
            raise UserError(_("Un journal validé ne peut plus être modifié."))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_unlocked()
        return lines

    def write(self, vals):
        self._check_unlocked()
        return super().write(vals)

    def unlink(self):
        self._check_unlocked()
        return super().unlink()


class MiroSiteJournalLabor(models.Model):
    _name = 'miro.site.journal.labor'
    _inherit = 'miro.site.journal.line'
    _description = "Main-d'œuvre du journal de chantier"

    employee_id = fields.Many2one('hr.employee', string="Ouvrier", required=True)
    hours = fields.Float(
        "Heures", required=True,
        default=lambda self: self.env.company.miro_hours_per_day or 8.0)
    hourly_cost = fields.Monetary(
        "Coût horaire", compute='_compute_hourly_cost', store=True, readonly=False,
        help="Coût horaire chargé de l'ouvrier (paie + charges patronales) au "
             "jour de la saisie ; il ne suit plus la paie une fois le journal validé.")
    cost = fields.Monetary("Coût", compute='_compute_cost', store=True)

    @api.depends('employee_id')
    def _compute_hourly_cost(self):
        for line in self:
            # sudo : les taux de paie sont réservés aux RH, pas au chef de chantier
            line.hourly_cost = line.employee_id.sudo()._miro_loaded_hourly_cost() \
                if line.employee_id else 0.0

    @api.depends('hours', 'hourly_cost')
    def _compute_cost(self):
        for line in self:
            line.cost = line.hours * line.hourly_cost

    @api.constrains('hours', 'employee_id', 'journal_id')
    def _check_hours(self):
        for line in self:
            if line.hours <= 0:
                raise ValidationError(_("Les heures de %s doivent être positives.")
                                      % line.employee_id.name)
            # Un ouvrier peut passer d'une phase à l'autre dans la journée
            total = sum(line.journal_id.work_ids.labor_line_ids.filtered(
                lambda l, e=line.employee_id: l.employee_id == e).mapped('hours'))
            if total > 24:
                raise ValidationError(_("%(name)s : %(hours)s h déclarées sur une seule journée.")
                                      % {'name': line.employee_id.name, 'hours': total})


class MiroSiteJournalMaterial(models.Model):
    _name = 'miro.site.journal.material'
    _inherit = 'miro.site.journal.line'
    _description = "Consommation du journal de chantier"

    need_id = fields.Many2one(
        'construction.material.need', string="Matériau", required=True,
        domain="[('task_id', '=', task_id), ('product_id', '!=', False)]")
    category_id = fields.Many2one(related='need_id.category_id', string="Besoin")
    product_id = fields.Many2one(related='need_id.product_id', string="Produit")
    uom_id = fields.Many2one(related='need_id.product_id.uom_id', string="Unité")
    need_qty = fields.Float(related='need_id.product_qty', string="Prévu (phase)")
    qty_remaining = fields.Float(related='need_id.qty_remaining', string="Reste à consommer")
    planned_qty = fields.Float(
        "Théorique", compute='_compute_planned_qty', digits='Product Unit of Measure',
        help="Ce que la quantité réalisée du jour aurait dû consommer d'après "
             "la nomenclature de la phase.")
    quantity = fields.Float("Consommé", digits='Product Unit of Measure')
    unit_cost = fields.Monetary(
        "Coût unitaire", compute='_compute_unit_cost', store=True, readonly=False)
    cost = fields.Monetary("Coût", compute='_compute_cost', store=True)

    @api.depends('need_id.product_qty', 'work_id.qty_done', 'work_id.phase_qty')
    def _compute_planned_qty(self):
        for line in self:
            phase_qty = line.work_id.phase_qty
            line.planned_qty = (line.need_id.product_qty * line.work_id.qty_done / phase_qty
                                if phase_qty else 0.0)

    @api.depends('need_id')
    def _compute_unit_cost(self):
        for line in self:
            line.unit_cost = line.need_id.product_id.standard_price

    @api.depends('quantity', 'unit_cost')
    def _compute_cost(self):
        for line in self:
            line.cost = line.quantity * line.unit_cost

    @api.constrains('quantity')
    def _check_quantity(self):
        if any(line.quantity < 0 for line in self):
            raise ValidationError(_("Une quantité consommée ne peut pas être négative."))


class MiroSiteJournalEquipment(models.Model):
    _name = 'miro.site.journal.equipment'
    _inherit = 'miro.site.journal.line'
    _description = "Matériel du journal de chantier"

    equipment_id = fields.Many2one('miro.site.equipment', string="Matériel", required=True)
    hours = fields.Float("Heures", required=True)
    hourly_cost = fields.Monetary(
        "Coût horaire", compute='_compute_hourly_cost', store=True, readonly=False)
    cost = fields.Monetary("Coût", compute='_compute_cost', store=True)

    @api.depends('equipment_id')
    def _compute_hourly_cost(self):
        for line in self:
            line.hourly_cost = line.equipment_id.hourly_cost

    @api.depends('hours', 'hourly_cost')
    def _compute_cost(self):
        for line in self:
            line.cost = line.hours * line.hourly_cost


class MiroSiteJournalExpense(models.Model):
    _name = 'miro.site.journal.expense'
    _inherit = 'miro.site.journal.line'
    _description = "Dépense du journal de chantier"

    name = fields.Char("Dépense", required=True)
    partner_id = fields.Many2one('res.partner', string="Payé à")
    amount = fields.Monetary("Montant", required=True)
