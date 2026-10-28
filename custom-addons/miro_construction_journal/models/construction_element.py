from odoo import api, models


class ConstructionElement(models.Model):
    _inherit = 'construction.element'

    @api.depends('task_ids.x_avancement_global', 'task_ids.x_poids_avancement', 'task_ids.state')
    def _compute_progress(self):
        """Moyenne des phases de l'élément pondérée par leur coût prévu."""
        Task = self.env['project.task']
        for rec in self:
            rec.progress = Task._weighted_progress(
                rec.task_ids.filtered(lambda t: t.state != '1_canceled'))
