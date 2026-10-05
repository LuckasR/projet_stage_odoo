# -*- coding: utf-8 -*-
from odoo import models, fields


class ConstructionPlanLevel(models.Model):
    _name = "construction.plan.level"
    _description = "Niveau de plan"
    _order = "sequence, name"

    name = fields.Char("Niveau", required=True, translate=True)
    code = fields.Char("Code", help="Ex : RDC, R+1, SS1")
    sequence = fields.Integer("Séquence", default=10)
    elevation = fields.Float("Altitude (m)", help="Altitude du niveau fini, en mètres")
    color = fields.Integer("Couleur")

    active = fields.Boolean("Actif", default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Ce niveau existe déjà."),
    ]