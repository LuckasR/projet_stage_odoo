from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class ConstructionElement(models.Model):
    _inherit = 'construction.element'

    key = fields.Char("Clé d'identification", index=True, copy=False,
                      help="Identifiant stable dans le projet (ex. : S1). "
                           "Sert à mettre à jour l'élément lors d'une nouvelle révision du plan.")
    type_id = fields.Many2one('construction.element.type', string="Type d'élément")
    source_file_id = fields.Many2one('construction.file', string="Plan source", readonly=True)
    source_page = fields.Integer("Page source", readonly=True)
    confidence = fields.Float("Confiance de l'analyse", digits=(3, 2), readonly=True)

    qty_beton_m3 = fields.Float("Béton (m³)")
    qty_acier_kg = fields.Float("Acier (kg)")
    qty_coffrage_m2 = fields.Float("Coffrage (m²)")

    task_ids = fields.One2many('project.task', 'element_id', string="Phases")
    task_count = fields.Integer(compute='_compute_task_count')
    progress = fields.Float("Avancement (%)", compute='_compute_progress')

    @api.depends('task_ids')
    def _compute_task_count(self):
        for rec in self:
            rec.task_count = len(rec.task_ids)

    @api.depends('task_ids.state', 'task_ids.allocated_hours')
    def _compute_progress(self):
        """Moyenne pondérée par les heures prévues (poids 1 si non renseignées)."""
        for rec in self:
            tasks = rec.task_ids.filtered(lambda t: t.state != '1_canceled')
            total = sum(t.allocated_hours or 1.0 for t in tasks)
            done = sum(t.allocated_hours or 1.0 for t in tasks if t.state == '1_done')
            rec.progress = 100.0 * done / total if total else 0.0

    @api.constrains('key', 'work_id')
    def _check_key_unique_per_project(self):
        for rec in self.filtered('key'):
            project = rec.work_id.project_id
            if not project:
                continue
            dup = self.search_count([
                ('id', '!=', rec.id),
                ('key', '=', rec.key),
                ('work_id.project_id', '=', project.id)])
            if dup:
                raise ValidationError(_(
                    "La clé « %s » existe déjà dans le projet « %s ».")
                    % (rec.key, project.name))

    # ------------------------------------------------------------------
    # Génération des phases depuis le gabarit du type
    # ------------------------------------------------------------------
    def _generate_tasks(self):
        """Crée les phases manquantes (idempotent), en un seul create groupé,
        puis pose les dépendances entre phases. Ne supprime jamais rien."""
        Task = self.env['project.task']
        vals_list, meta = [], []

        for element in self:
            project = element.work_id.project_id
            template = element.type_id.phase_template_id
            if not project or not template:
                continue
            existing_types = set(element.task_ids.mapped('phase_type'))
            for line in template.line_ids.sorted('sequence'):
                if line.phase_type in existing_types:
                    continue
                vals_list.append({
                    'name': "%s - %s" % (element.key or element.display_name, line.name),
                    'project_id': project.id,
                    'element_id': element.id,
                    'phase_type': line.phase_type,
                    'phase_template_line_id': line.id,
                    'allocated_hours': line._compute_hours(element),
                    'parent_id': element.work_id.id,
                })
                meta.append((element, line))

        if not vals_list:
            return Task
        tasks = Task.create(vals_list)

        if 'depend_on_ids' in Task._fields:
            created = {(el.id, line.id): task for (el, line), task in zip(meta, tasks)}
            for (element, line), task in zip(meta, tasks):
                dep_line = line.depends_on_line_id
                if not dep_line:
                    continue
                previous = created.get((element.id, dep_line.id)) or \
                    element.task_ids.filtered(
                        lambda t: t.phase_template_line_id == dep_line)[:1]
                if previous:
                    task.write({'depend_on_ids': [Command.link(previous.id)]})
        return tasks

    def action_generate_tasks(self):
        self._generate_tasks()

    def action_view_tasks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Phases"),
            'res_model': 'project.task',
            'view_mode': 'tree,form',
            'domain': [('element_id', '=', self.id)],
            'context': {'default_element_id': self.id,
                        'default_project_id': self.work_id.project_id.id},
        }
