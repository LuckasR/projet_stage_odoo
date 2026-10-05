# -*- coding: utf-8 -*-
from odoo import models, fields


class ConstructionPlanView(models.Model):
    _name = "construction.plan.view"
    _description = "Type de vue de plan"
    _order = "sequence, name"

    name = fields.Char("Type de vue", required=True, translate=True)
    code = fields.Char("Code", help="Ex : PLAN, COUPE, FACADE")
    sequence = fields.Integer("Séquence", default=10)
    color = fields.Integer("Couleur")
    active = fields.Boolean("Actif", default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Ce type de vue existe déjà."),
    ]
