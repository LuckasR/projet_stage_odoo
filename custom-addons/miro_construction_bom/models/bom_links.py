from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ConstructionPhaseTemplateLine(models.Model):
    """Une phase consomme des matériaux : sa nomenclature dit lesquels, pour
    une unité du métré sur lequel elle travaille (`qty_key`)."""
    _inherit = 'construction.phase.template.line'

    qty_key = fields.Selection(
        selection_add=[('surface_m2', "Surface (m²)")],
        ondelete={'surface_m2': 'set null'})
    bom_id = fields.Many2one(
        'mrp.bom', string="Nomenclature", domain=[('construction_ok', '=', True)],
        help="Matériaux consommés pour UNE unité de la quantité de référence "
             "de la phase (1 m³ de béton coulé, 1 kg d'acier posé, 1 m² "
             "coffré...). Un type d'élément peut en imposer une autre.")

    @api.constrains('bom_id', 'qty_key')
    def _check_bom_unit(self):
        for line in self.filtered('bom_id'):
            if not line.qty_key:
                raise ValidationError(_(
                    "La phase « %s » doit avoir une quantité de référence pour "
                    "porter une nomenclature.") % line.name)
            self.env['mrp.bom']._check_unit_for(line.bom_id, line.qty_key, line.name)


class ConstructionElementTypeBom(models.Model):
    """Nomenclature imposée par un type d'élément pour l'une de ses phases :
    le gabarit « Semelle » sert aussi aux longrines, mais une semelle se
    coule en C20/25 et un poteau en C25/30."""
    _name = 'construction.element.type.bom'
    _description = "Nomenclature d'une phase pour un type d'élément"
    _order = 'type_id, phase_type'

    type_id = fields.Many2one(
        'construction.element.type', required=True, ondelete='cascade', index=True)
    phase_line_id = fields.Many2one(
        'construction.phase.template.line', string="Phase", required=True,
        ondelete='cascade',
        domain="[('template_id', '=', parent.phase_template_id)]")
    phase_type = fields.Char(related='phase_line_id.phase_type', store=True)
    bom_id = fields.Many2one('mrp.bom', string="Nomenclature", required=True,
                             domain=[('construction_ok', '=', True)])

    _sql_constraints = [
        ('phase_uniq', 'unique(type_id, phase_line_id)',
         "Une seule nomenclature par phase pour un type d'élément."),
    ]

    @api.constrains('bom_id', 'phase_line_id')
    def _check_bom_unit(self):
        for rec in self:
            self.env['mrp.bom']._check_unit_for(
                rec.bom_id, rec.phase_line_id.qty_key, rec.phase_line_id.name)


class ConstructionElementType(models.Model):
    _inherit = 'construction.element.type'

    bom_override_ids = fields.One2many(
        'construction.element.type.bom', 'type_id',
        string="Nomenclatures propres au type")

    def _bom_for(self, phase_line):
        """Nomenclature d'une phase pour ce type : celle du type si elle
        existe, sinon celle du gabarit."""
        self.ensure_one()
        override = self.bom_override_ids.filtered(lambda o: o.phase_line_id == phase_line)
        return override[:1].bom_id or phase_line.bom_id
