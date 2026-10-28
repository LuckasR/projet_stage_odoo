from odoo import _, api, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    miro_journal_ids = fields.One2many('miro.site.journal', 'project_id', string="Journaux de chantier")
    miro_journal_count = fields.Integer(compute='_compute_miro_journal_count')
    miro_journal_to_validate = fields.Integer(compute='_compute_miro_journal_count')

    x_cout_mo_reel_total = fields.Monetary(
        "Main-d'œuvre réelle", compute='_compute_couts', store=True, currency_field='currency_id')
    x_cout_matiere_reel_total = fields.Monetary(
        "Matières réelles", compute='_compute_couts', store=True, currency_field='currency_id')
    x_cout_materiel_reel_total = fields.Monetary(
        "Matériel réel", compute='_compute_couts', store=True, currency_field='currency_id')
    x_cout_divers_reel_total = fields.Monetary(
        "Frais divers réels", compute='_compute_couts', store=True, currency_field='currency_id')

    def _compute_miro_journal_count(self):
        for project in self:
            journals = project.miro_journal_ids
            project.miro_journal_count = len(journals)
            project.miro_journal_to_validate = len(journals.filtered(lambda j: j.state == 'submitted'))

    @api.depends('tasks.x_cout_prevue', 'tasks.x_cout_mo_reel', 'tasks.x_cout_matiere_reel',
                 'tasks.x_cout_materiel_reel', 'tasks.x_cout_divers_reel',
                 'miro_journal_ids.site_equipment_line_ids.state',
                 'miro_journal_ids.site_equipment_line_ids.cost',
                 'miro_journal_ids.site_expense_line_ids.state',
                 'miro_journal_ids.site_expense_line_ids.amount')
    def _compute_couts(self):
        """Coût réel : chaque tâche n'y compte que pour ses propres lignes
        (x_cout_reel d'une tâche mère inclut ses filles : l'additionner sur
        toutes les tâches compterait deux fois). Le matériel et les dépenses
        du journal sans phase sont des frais du chantier."""
        for project in self:
            tasks = project.tasks
            journals = project.miro_journal_ids
            site_equipment = sum(journals.site_equipment_line_ids.filtered(
                lambda l: l.state == 'validated').mapped('cost'))
            site_expense = sum(journals.site_expense_line_ids.filtered(
                lambda l: l.state == 'validated').mapped('amount'))
            project.x_cout_prevue_total = sum(tasks.mapped('x_cout_prevue'))
            project.x_cout_mo_reel_total = sum(tasks.mapped('x_cout_mo_reel'))
            project.x_cout_matiere_reel_total = sum(tasks.mapped('x_cout_matiere_reel'))
            project.x_cout_materiel_reel_total = sum(tasks.mapped('x_cout_materiel_reel')) + site_equipment
            project.x_cout_divers_reel_total = sum(tasks.mapped('x_cout_divers_reel')) + site_expense
            project.x_cout_reel_total = (project.x_cout_mo_reel_total + project.x_cout_matiere_reel_total
                                         + project.x_cout_materiel_reel_total
                                         + project.x_cout_divers_reel_total)

    @api.depends('tasks.x_avancement_global', 'tasks.x_poids_avancement', 'tasks.parent_id')
    def _compute_avancement_global(self):
        """Moyenne des tâches racines pondérée par leur coût prévu."""
        Task = self.env['project.task']
        for project in self:
            project.x_avancement_global = Task._weighted_progress(
                project.tasks.filtered(lambda t: not t.parent_id))

    def action_open_site_journals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Journaux — %s") % self.name,
            'res_model': 'miro.site.journal',
            'view_mode': 'tree,calendar,form',
            'views': [(False, 'tree'), (False, 'calendar'), (False, 'form')],
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
