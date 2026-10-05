from odoo import fields, models

class ConstructionMaterialCategory(models.Model):
    _name = 'construction.material.category'
    _description = 'Catégorie de matériau de construction'
    _order = 'sequence, name'

    name = fields.Char(
        string="Nom",
        required=True,
        index=True,
    )

    code = fields.Char(
        string="Code",
        required=True,
        index=True,
    )

    sequence = fields.Integer(
        string="Séquence",
        default=10,
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    parent_id = fields.Many2one(
        'construction.material.category',
        string="Catégorie parente",
        ondelete='restrict',
    )

    child_ids = fields.One2many(
        'construction.material.category',
        'parent_id',
        string="Sous-catégories",
    )

    description = fields.Text(
        string="Description",
    )