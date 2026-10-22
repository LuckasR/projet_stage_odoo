from odoo import api, fields, models


class ProjectTask(models.Model):
    """Coût réel d'une tâche, calculé et jamais saisi : journaux de chantier
    validés pour la main-d'œuvre, le matériel et les dépenses ; sorties de
    stock pour les matières. Une tâche mère cumule ses sous-tâches."""
    _inherit = 'project.task'

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
            # Toute sortie de stock vers le chantier, qu'elle vienne d'un
            # journal ou de « Déclarer la consommation »
            task.x_cout_matiere_reel = sum(
                m.product_uom._compute_quantity(m.quantity, m.product_id.uom_id, round=False)
                * (m.price_unit or m.product_id.standard_price)
                for m in task.material_need_ids.move_ids if m.state == 'done')

    @api.depends('x_cout_mo_reel', 'x_cout_matiere_reel', 'x_cout_materiel_reel',
                 'x_cout_divers_reel', 'child_ids.x_cout_reel')
    def _compute_cout_reel(self):
        for task in self:
            task.x_cout_reel = (task.x_cout_mo_reel + task.x_cout_matiere_reel
                                + task.x_cout_materiel_reel + task.x_cout_divers_reel
                                + sum(task.child_ids.mapped('x_cout_reel')))
