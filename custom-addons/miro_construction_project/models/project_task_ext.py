from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    is_ouvrage = fields.Boolean(
        "Ouvrage", index=True, copy=False,
        help="Task de regroupement d'un ouvrage (Fondation, Élévation…). "
             "Ses sous-tâches sont les phases des éléments de construction.")
    construction_element_id = fields.Many2one(
        'construction.element', string="Élément de construction",
        index=True, ondelete='restrict')
    phase_type = fields.Char("Code de phase", index=True)
    phase_template_line_id = fields.Many2one(
        'construction.phase.template.line', string="Ligne de gabarit", ondelete='set null')
