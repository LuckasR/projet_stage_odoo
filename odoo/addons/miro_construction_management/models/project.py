from odoo import models, fields

class Project(models.Model):
    _inherit = "project.project"

    construction_code = fields.Char("Code chantier")

    site_address = fields.Char("Adresse")

    dxf_file_ids = fields.One2many(
        "construction.dxf.file",
        "project_id",
        string="Fichiers DXF"
    )