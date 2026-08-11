from odoo import models, fields

class ConstructionProject(models.Model):
    _inherit = "project.project"

    construction_code = fields.Char(
        string="Code chantier"
    )

    site_address = fields.Text(
        string="Adresse du chantier"
    )

    estimated_budget = fields.Float(
        string="Budget estimé"
    )

    actual_budget = fields.Float(
        string="Budget réel"
    )
    

