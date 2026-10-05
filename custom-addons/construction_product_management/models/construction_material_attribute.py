# -*- coding: utf-8 -*-
from odoo import fields, models


class ConstructionMaterialAttribute(models.Model):
    """Définit une caractéristique mesurable réutilisable :
    largeur, hauteur, épaisseur, diamètre, masse, volume,
    résistance, granulométrie, etc.
    """
    _name = 'construction.material.attribute'
    _description = "Caractéristique de matériau de construction"
    _order = 'sequence, id'

    name = fields.Char(string="Nom", required=True, translate=True)
    code = fields.Char(
        string="Code technique",
        required=True,
        help="Identifiant unique (ex: width, height, diameter, resistance_class).",
    )
    sequence = fields.Integer(default=10)

    value_type = fields.Selection(
        selection=[
            ('float', 'Numérique'),
            ('char', 'Texte'),
            ('selection', 'Liste de choix'),
        ],
        string="Type de valeur",
        default='float',
        required=True,
    )

    uom_id = fields.Many2one(
        'uom.uom',
        string="Unité de mesure",
        help="Ex: mm, cm, m, kg, m³. Laisser vide si non numérique.",
    )

    selection_option_ids = fields.One2many(
        'construction.material.attribute.option',
        'attribute_id',
        string="Options possibles",
        help="Utilisé uniquement si le type de valeur est 'Liste de choix'.",
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', "Le code technique doit être unique."),
    ]


class ConstructionMaterialAttributeOption(models.Model):
    """Options possibles pour un attribut de type 'selection'
    (ex: nuance d'acier Fe E400 / Fe E500, type de ciment CPA/CPJ...).
    """
    _name = 'construction.material.attribute.option'
    _description = "Option de caractéristique"
    _order = 'sequence, id'

    attribute_id = fields.Many2one(
        'construction.material.attribute',
        string="Caractéristique",
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(string="Valeur", required=True, translate=True)
    sequence = fields.Integer(default=10)
