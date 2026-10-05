from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    element_id = fields.Many2one(
        'construction.element', string="Élément de construction",
        index=True, ondelete='restrict')
    phase_type = fields.Char("Code de phase", index=True)
    phase_template_line_id = fields.Many2one(
        'construction.phase.template.line', string="Ligne de gabarit", ondelete='set null')
