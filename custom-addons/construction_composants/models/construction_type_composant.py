# -*- coding: utf-8 -*-
from odoo import models, fields


class ConstructionTypeComposant(models.Model):
    _name = 'construction.type.composant'
    _description = "Type de composant (Semelle, Mur, Poteau, Dalle...)"

    name = fields.Char(string="Nom", required=True)
    code = fields.Char(string="Code")
    gere_les_faces = fields.Boolean(
        string="Gère les faces",
        help="À cocher pour les types comme Mur, où l'orientation "
             "(Nord/Sud/Est/Ouest, intérieure/extérieure) compte."
    )
    attribut_ids = fields.One2many(
        'construction.type.composant.attribut', 'type_id',
        string="Attributs de dimension attendus"
    )

    _sql_constraints = [
        ('name_uniq', 'unique(name)', "Ce type de composant existe déjà."),
    ]


class ConstructionTypeComposantAttribut(models.Model):
    _name = 'construction.type.composant.attribut'
    _description = "Attribut de dimension attendu pour un type de composant"
    _order = 'sequence, id'

    type_id = fields.Many2one(
        'construction.type.composant', required=True, ondelete='cascade'
    )
    name = fields.Char(
        string="Attribut", required=True,
        help="Ex : longueur, largeur, hauteur, épaisseur"
    )
    unite = fields.Selection([
        ('m', 'Mètre'),
        ('cm', 'Centimètre'),
        ('mm', 'Millimètre'),
    ], string="Unité", default='m', required=True)
    sequence = fields.Integer(default=10)
