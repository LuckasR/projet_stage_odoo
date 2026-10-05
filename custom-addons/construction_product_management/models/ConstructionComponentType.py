from odoo import models, fields


class ConstructionComponentType(models.Model):
    _name = 'construction.component.type'
    _description = "Type d'ouvrage"

    name = fields.Char(
        string='Nom',
        required=True
    )

    code = fields.Char(
        string='Code'
    )

    active = fields.Boolean(
        default=True
    )