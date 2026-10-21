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

    # --- Élément de la phase et ses métrés (affichage dans la fiche) -----
    element_type_id = fields.Many2one(
        related='construction_element_id.element_type_id', string="Type d'élément")
    element_level_id = fields.Many2one(
        related='construction_element_id.level_id', string="Niveau")
    element_dimension_summary = fields.Char(
        related='construction_element_id.dimension_summary', string="Cotes")
    element_qty_beton_m3 = fields.Float(
        related='construction_element_id.qty_beton_m3', string="Volume béton (m³)")
    element_qty_coffrage_m2 = fields.Float(
        related='construction_element_id.qty_coffrage_m2', string="Surface coffrée (m²)")
    element_qty_surface_m2 = fields.Float(
        related='construction_element_id.qty_surface_m2', string="Surface (m²)")
    element_qty_acier_kg = fields.Float(
        related='construction_element_id.qty_acier_kg', string="Acier (kg)")
    phase_qty = fields.Float(
        "Quantité de la phase", compute='_compute_phase_qty', digits=(16, 3),
        help="Métré de l'élément sur lequel travaille cette phase (béton pour un "
             "coulage, coffrage pour un coffrage...).")
    phase_qty_label = fields.Char("Unité de la phase", compute='_compute_phase_qty')

    def _compute_phase_qty(self):
        for task in self:
            key = task.phase_template_line_id.qty_key
            element = task.construction_element_id
            if key and element:
                task.phase_qty = getattr(element, 'qty_%s' % key, 0.0) or 0.0
                task.phase_qty_label = dict(
                    task.phase_template_line_id._fields['qty_key']._description_selection(self.env)
                ).get(key, key)
            else:
                task.phase_qty = 0.0
                task.phase_qty_label = False
