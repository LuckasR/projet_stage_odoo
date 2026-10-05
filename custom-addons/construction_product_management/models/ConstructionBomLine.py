from odoo import fields, models


class ConstructionBomLine(models.Model):
    _name = 'construction.bom.line'
    _description = 'Ligne de nomenclature'
    _order = 'sequence, id'

    bom_id = fields.Many2one(
        'construction.bom',
        string='Nomenclature',
        required=True,
        ondelete='cascade'
    )

    sequence = fields.Integer(
        string='Séquence',
        default=10
    )

    component_id = fields.Many2one(
        'construction.material.category',
        string='Matériau Type',
        required=True
    )

    quantity = fields.Float(
        string='Quantité',
        required=True,
        default=1.0
    )

    unit_id = fields.Many2one(
        'uom.uom',
        string='Unité',
        required=True,
        ondelete='restrict'
    )

    coefficient = fields.Float(
        string='Coefficient',
        default=1.0
    )

    notes = fields.Text(
        string='Notes'
    )