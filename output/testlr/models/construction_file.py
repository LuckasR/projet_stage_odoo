from odoo import api, models, fields

class ConstructionDxfFile(models.Model):
    _name = "construction.dxf.file"
    _description = "Gestion des fichiers DXF"
    _rec_name = "filename"

    filename = fields.Char(
        string="Nom du fichier",
        required=True
    )

    file = fields.Binary(
        string="Fichier DXF",
        required=True,
        attachment=True
    )

    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        required=True,
        ondelete="cascade"
    )

    imported_at = fields.Datetime(
        string="Date d'import",
        default=fields.Datetime.now,
        readonly=True
    )

    state = fields.Selection([
        ("draft", "Brouillon"),
        ("imported", "Importé"),
        ("analysed", "Analysé"),
        ("error", "Erreur"),
    ], default="draft")
    
    prix_ht = fields.Float(
        string="Prix HT",
        required=True,
        default=0.0
    )

    taxe = fields.Float(
        string="TVA (%)",
        default=20.0
    )

    # Prix TTC
    prix_ttc = fields.Float(
        string="Prix TTC",
        compute="_calc_prix_ttc",
        store=True,
        inverse="_set_prix_ttc"
    )

    @api.depends('prix_ht', 'taxe')
    def _calc_prix_ttc(self):
        for rec in self:
            rec.prix_ttc = rec.prix_ht * (1 + rec.taxe / 100)

    def _set_prix_ttc(self):
        """Inverse : quand on écrit prix_ttc, recalcule prix_ht"""
        for rec in self:
            rec.prix_ht = rec.prix_ttc / (1 + rec.taxe / 100)