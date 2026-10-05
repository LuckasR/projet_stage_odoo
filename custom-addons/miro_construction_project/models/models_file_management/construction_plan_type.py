# -*- coding: utf-8 -*-
from odoo import models, fields


class ConstructionPlanType(models.Model):
    _name = "construction.plan.type"
    _description = "Type de plan"
    _order = "sequence, name"

    name = fields.Char("Type de plan", required=True, translate=True)
    code = fields.Char("Code", help="Ex : ARCHI, COFFR, FOND")
    sequence = fields.Integer("Séquence", default=10)
    color = fields.Integer("Couleur")
    description = fields.Text("Description")
    analyzer = fields.Boolean(
        string="Analysable"
    )
    active = fields.Boolean("Actif", default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Ce type de plan existe déjà."),
    ]