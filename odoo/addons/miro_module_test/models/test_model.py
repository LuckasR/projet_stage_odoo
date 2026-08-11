from odoo import models, fields


class TestModel(models.Model):
    _name = "test.model"
    _description = "Test Model"

    name = fields.Char(
        string="Nom",
        required=True
    )

    description = fields.Text(
        string="Description"
    )