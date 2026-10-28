from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import format_date

# Phase sans métré : son avancement suit l'état déclaré
STATUS_PROGRESS = {'todo': 0.0, 'doing': 50.0, 'done': 100.0}

LINE_STATES = [('draft', "Brouillon"), ('validated', "Validé")]

# Ce qu'on peut encore écrire sur une ligne validée sans la déverrouiller
LINE_LOCK_FREE = {'sequence'}


def _line_validation_fields(self):
    return {'state': 'validated', 'validated_by_id': self.env.uid,
            'validated_on': fields.Datetime.now()}


def _line_reset_fields():
    return {'state': 'draft', 'validated_by_id': False, 'validated_on': False}


def _check_can_reset(env):
    if not env.user.has_group('project.group_project_manager'):
        raise AccessError(_("Seul le conducteur de travaux peut remettre une ligne validée en brouillon."))


class MiroSiteJournal(models.Model):
    """Journal de chantier : la journée d'un chantier, déclarée par le chef
    de chantier. Il regroupe les travaux du jour (une phase peut en avoir
    plusieurs), chacun avec sa main-d'œuvre, sa consommation, son matériel
    et ses dépenses.

    Le chef de chantier valide les lignes au fil de la journée : une ligne
    validée est figée et compte aussitôt (les matières sortent du stock,
    l'avancement et le coût réel sont mis à jour). On peut ajouter des
    lignes tant que le journal n'est pas validé ; soumettre ne fait que
    prévenir le conducteur. À la validation du journal (conducteur), les
    lignes restantes sont validées et plus rien ne bouge."""
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
        if self._validated_lines():
            raise UserError(_("Ce journal a des lignes validées : il ne peut plus être supprimé."))
        return super().unlink()

    def _validated_lines(self):
        """Lignes validées du journal, tous types confondus (une liste de
        recordsets : ils sont de modèles différents)."""
        works = self.work_ids
        lines = [works, works.labor_line_ids, works.material_line_ids, works.equipment_line_ids,
                 works.expense_line_ids, self.site_equipment_line_ids, self.site_expense_line_ids]
        return [validated for validated in (l.filtered(lambda r: r.state == 'validated') for l in lines)
                if validated]

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
        """Fige le journal : les lignes pas encore validées le sont (leurs
        matières sortent du stock), puis plus rien ne bouge."""
        self._check_state('draft', 'submitted')
        self._check_not_empty()
        for journal in self.sorted('date'):
            journal.work_ids.action_validate_line()
            journal.site_equipment_line_ids.action_validate_line()
            journal.site_expense_line_ids.action_validate_line()
            journal.with_context(miro_journal_unlocked=True).write({
                'state': 'validated', 'validated_by_id': self.env.uid,
                'validated_on': fields.Datetime.now()})
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
    """Travail du jour sur une phase : ce qui a été réalisé, et ce que ça a
    demandé — ouvriers, matières de la phase, matériel, dépenses. Une phase
    peut avoir plusieurs travaux le même jour (le matin validé, l'après-midi
    dans une nouvelle ligne).

    Valider le travail le fige avec toutes ses lignes ; son réalisé compte
    alors dans l'avancement de la phase. Chaque ligne (un ouvrier, une
    matière...) peut aussi être validée seule, avant le travail.

    Le réalisé est la seule source de l'avancement d'une phase : une
    quantité dans l'unité de la phase (m³ coulés...), ou pour une phase sans
    métré un état (pas commencé / en cours / fini). Une erreur se corrige
    par une quantité négative, avec son motif, dans un journal suivant."""
    _name = 'miro.site.journal.work'
    _description = "Travail du journal de chantier"
    _order = 'journal_id, sequence, id'
    _rec_name = 'task_id'

    journal_id = fields.Many2one('miro.site.journal', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    project_id = fields.Many2one(related='journal_id.project_id', store=True, string="Chantier")
    date = fields.Date(related='journal_id.date', store=True)
    state = fields.Selection(LINE_STATES, string="État", default='draft', required=True,
                             readonly=True, copy=False, index=True)
    journal_state = fields.Selection(related='journal_id.state', string="État du journal")
    validated_by_id = fields.Many2one('res.users', string="Validé par", readonly=True, copy=False)
    validated_on = fields.Datetime("Validé le", readonly=True, copy=False)
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
    qty_done = fields.Float(
        "Réalisé ce jour", digits=(16, 3),
        help="Négatif pour corriger un réalisé déclaré en trop (motif obligatoire).")
    correction_reason = fields.Char("Motif de la correction")
    status = fields.Selection([
        ('todo', "Pas commencé"),
        ('doing', "En cours"),
        ('done', "Fini"),
    ], string="État de la phase", default='doing',
        help="Pour une phase sans métré : état à la fin de la journée.")
    progress_after = fields.Float("Avancement après (%)", compute='_compute_progress')
    check_html = fields.Html("Contrôles", compute='_compute_check_html', sanitize=False)
    note = fields.Char("Remarque")

    # --- Ce que le travail a demandé ---------------------------------------
    labor_line_ids = fields.One2many('miro.site.journal.labor', 'work_id', string="Main-d'œuvre")
    material_line_ids = fields.One2many('miro.site.journal.material', 'work_id', string="Consommation")
    equipment_line_ids = fields.One2many('miro.site.journal.equipment', 'work_id', string="Matériel")
    expense_line_ids = fields.One2many('miro.site.journal.expense', 'work_id', string="Dépenses")

    headcount = fields.Integer("Ouvriers", compute='_compute_totals', store=True)
    labor_hours = fields.Float("Heures", compute='_compute_totals', store=True)
    total_cost = fields.Monetary("Coût", compute='_compute_totals', store=True)

    @api.depends('task_id', 'qty_done', 'status', 'date')
    def _compute_progress(self):
        Work = self.env['miro.site.journal.work']
        for work in self:
            before = Work.search([
                ('task_id', '=', work.task_id.id), ('state', '=', 'validated'),
                ('id', '!=', work._origin.id or 0)]) if work.task_id else Work
            work.qty_before = sum(before.mapped('qty_done'))
            if work.phase_qty:
                work.progress_after = min(max(
                    100.0 * (work.qty_before + work.qty_done) / work.phase_qty, 0.0), 100.0)
            else:
                work.progress_after = STATUS_PROGRESS.get(work.status, 0.0)

    @api.depends('task_id', 'qty_done', 'status', 'labor_line_ids.hours',
                 'material_line_ids.quantity', 'state')
    def _compute_check_html(self):
        """Ce que donnerait la phase avec ce travail : les contrôles de
        cohérence de la phase, avant même la validation."""
        for work in self:
            if not work.task_id:
                work.check_html = False
                continue
            pending = work.state != 'validated'
            alerts = work.task_id._progress_checks(
                progress=work.progress_after,
                extra_hours=sum(work.labor_line_ids.mapped('hours')) if pending else 0.0,
                extra_material={l.need_id: l.quantity for l in work.material_line_ids} if pending else None,
                extra_qty=work.qty_done if pending else 0.0)
            work.check_html = work.task_id._progress_checks_html(alerts)

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

    @api.constrains('qty_done', 'correction_reason')
    def _check_values(self):
        for work in self:
            if work.qty_done >= 0:
                continue
            if not (work.correction_reason or '').strip():
                raise ValidationError(_(
                    "%s : une quantité négative corrige un réalisé déclaré en trop ; "
                    "indiquez le motif de la correction.") % work.task_id.display_name)
            if work.qty_before + work.qty_done < -1e-6:
                raise ValidationError(_(
                    "%(task)s : la correction (%(qty)s) dépasse ce qui a été réalisé (%(done)s).")
                    % {'task': work.task_id.display_name, 'qty': work.qty_done,
                       'done': work.qty_before})

    def _sub_lines(self):
        return [self.labor_line_ids, self.material_line_ids, self.equipment_line_ids,
                self.expense_line_ids]

    def _check_unlocked(self, vals=None):
        if self.env.context.get('miro_journal_unlocked'):
            return
        if self.journal_id.filtered(lambda j: j.state == 'validated'):
            raise UserError(_("Un journal validé ne peut plus être modifié."))
        validated = self.filtered(lambda w: w.state == 'validated')
        if validated and (vals is None or set(vals) - LINE_LOCK_FREE):
            raise UserError(_("%s : ce travail est validé, il ne peut plus être modifié. "
                              "Ajoutez une nouvelle ligne.") % validated[0].task_id.display_name)

    @api.model_create_multi
    def create(self, vals_list):
        works = super().create(vals_list)
        works._check_unlocked()
        return works

    def write(self, vals):
        self._check_unlocked(vals)
        return super().write(vals)

    def unlink(self):
        self._check_unlocked()
        if any(lines.filtered(lambda l: l.state == 'validated') for lines in self._sub_lines()):
            raise UserError(_("Ce travail a des lignes validées : il ne peut plus être supprimé."))
        return super().unlink()

    def action_validate_line(self):
        """Valide le travail et toutes ses lignes : il est figé, son réalisé
        compte dans l'avancement, ses matières sortent du stock."""
        works = self.filtered(lambda w: w.state == 'draft')
        if works.journal_id.filtered(lambda j: j.state == 'validated'):
            raise UserError(_("Le journal est validé."))
        for work in works:
            for lines in work._sub_lines():
                lines.action_validate_line()
            work.with_context(miro_journal_unlocked=True).write(_line_validation_fields(work))
        return True

    def action_reset_line(self):
        """Conducteur de travaux : remet le travail et ses lignes en
        brouillon ; les matières sorties reviennent en stock."""
        _check_can_reset(self.env)
        works = self.filtered(lambda w: w.state == 'validated')
        if works.journal_id.filtered(lambda j: j.state == 'validated'):
            raise UserError(_("Le journal est validé : ses lignes ne peuvent plus être remises en brouillon."))
        for work in works:
            work.with_context(miro_journal_unlocked=True).write(_line_reset_fields())
            for lines in work._sub_lines():
                lines.action_reset_line()
        return True


class MiroSiteJournalLine(models.AbstractModel):
    """Ce que toutes les lignes d'un journal ont en commun : rattachées à un
    travail (donc à sa phase) ou, pour le matériel et les dépenses, au
    chantier entier ; leur validation une à une, et les verrous (ligne
    validée, travail validé, journal validé)."""
    _name = 'miro.site.journal.line'
    _description = "Ligne de journal de chantier"

    work_id = fields.Many2one('miro.site.journal.work', string="Travail", ondelete='cascade', index=True)
    journal_id = fields.Many2one(
        'miro.site.journal', compute='_compute_journal_id', store=True, readonly=False,
        precompute=True, required=True, ondelete='cascade', index=True)
    task_id = fields.Many2one(related='work_id.task_id', store=True, string="Phase", index=True)
    project_id = fields.Many2one(related='journal_id.project_id', store=True, string="Chantier")
    date = fields.Date(related='journal_id.date', store=True)
    state = fields.Selection(LINE_STATES, string="État", default='draft', required=True,
                             readonly=True, copy=False, index=True)
    journal_state = fields.Selection(related='journal_id.state', string="État du journal")
    validated_by_id = fields.Many2one('res.users', string="Validé par", readonly=True, copy=False)
    validated_on = fields.Datetime("Validé le", readonly=True, copy=False)
    currency_id = fields.Many2one(related='journal_id.currency_id')

    @api.depends('work_id')
    def _compute_journal_id(self):
        for line in self.filtered('work_id'):
            line.journal_id = line.work_id.journal_id

    def _check_unlocked(self, vals=None):
        if self.env.context.get('miro_journal_unlocked'):
            return
        if self.journal_id.filtered(lambda j: j.state == 'validated'):
            raise UserError(_("Un journal validé ne peut plus être modifié."))
        if self.work_id.filtered(lambda w: w.state == 'validated'):
            raise UserError(_("Ce travail est validé : ajoutez une nouvelle ligne de travail."))
        if self.filtered(lambda l: l.state == 'validated') and (vals is None or set(vals) - LINE_LOCK_FREE):
            raise UserError(_("Cette ligne est validée : elle ne peut plus être modifiée."))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_unlocked()
        return lines

    def write(self, vals):
        self._check_unlocked(vals)
        return super().write(vals)

    def unlink(self):
        self._check_unlocked()
        return super().unlink()

    def action_validate_line(self):
        lines = self.filtered(lambda l: l.state == 'draft')
        if lines.journal_id.filtered(lambda j: j.state == 'validated'):
            raise UserError(_("Le journal est validé."))
        for line in lines:
            line._on_validate()
            line.with_context(miro_journal_unlocked=True).write(_line_validation_fields(line))
        return True

    def action_reset_line(self):
        _check_can_reset(self.env)
        lines = self.filtered(lambda l: l.state == 'validated')
        if lines.journal_id.filtered(lambda j: j.state == 'validated'):
            raise UserError(_("Le journal est validé : ses lignes ne peuvent plus être remises en brouillon."))
        if not self.env.context.get('miro_journal_unlocked') \
                and lines.work_id.filtered(lambda w: w.state == 'validated'):
            raise UserError(_("Remettez d'abord le travail en brouillon."))
        for line in lines:
            line._on_reset()
            line.with_context(miro_journal_unlocked=True).write(_line_reset_fields())
        return True

    def _on_validate(self):
        """Ce que la validation déclenche, en plus de figer la ligne."""

    def _on_reset(self):
        """Annule ce que _on_validate a déclenché."""


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
    move_ids = fields.Many2many('stock.move', string="Sorties de stock", readonly=True, copy=False)
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

    def _on_validate(self):
        Need = self.env['construction.material.need']
        for line in self.filtered(lambda l: l.quantity > 0):
            moves = Need._consume({line.need_id: line.quantity}, line.journal_id.location_id,
                                  origin=line.journal_id.name)
            line.with_context(miro_journal_unlocked=True).move_ids = moves

    def _on_reset(self):
        """La matière sortie revient dans l'emplacement d'où elle était partie."""
        Need = self.env['construction.material.need']
        for line in self.filtered('move_ids'):
            done = line.move_ids.filtered(lambda m: m.state == 'done')
            Need._consume({line.need_id: sum(done.mapped('quantity'))}, line.journal_id.location_id,
                          origin=_("Annulation — %s") % line.journal_id.name, reverse=True)
            line.with_context(miro_journal_unlocked=True).move_ids = False


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
