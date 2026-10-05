# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ConstructionMaterialType(models.Model):
    """Catalogue des sous-types de matériaux de construction.

    Permet à l'utilisateur de définir ses propres sous-types
    (ex: 'Ciment CPJ 45', 'Sable de rivière 0/4', 'Gravier 8/15')
    rattachés à une catégorie générale (ciment, sable, gravier...).
    """
    _name = 'construction.material.type'
    _description = "Type de matériau de construction"
    _order = 'category, sequence, name'

    name = fields.Char(string="Nom du type", required=True, translate=True)
    sequence = fields.Integer(default=10)
    category = fields.Selection(
        selection=[
            ('ciment', 'Ciment'),
            ('sable', 'Sable'),
            ('gravier', 'Gravier / Gravillon'),
            ('acier', 'Acier / Fer à béton'),
            ('bois', 'Bois'),
            ('brique', 'Brique'),
            ('parpaing', 'Parpaing / Bloc'),
            ('carrelage', 'Carrelage / Revêtement'),
            ('peinture', 'Peinture'),
            ('autre', 'Autre'),
        ],
        string="Catégorie",
        required=True,
        default='autre',
    )
    active = fields.Boolean(default=True)
    description = fields.Text(string="Description")
    product_tmpl_ids = fields.One2many(
        'product.template', 'construction_material_type_id',
        string="Produits liés",
    )
    product_count = fields.Integer(
        string="Nb. produits", compute='_compute_product_count'
    )
    attribute_ids = fields.Many2many(
        'construction.material.attribute',
        string="Caractéristiques applicables",
        help="Ex: pour 'Fer à béton' -> diamètre, longueur, nuance. "
             "Pour 'Parpaing' -> largeur, hauteur, épaisseur, masse.",
    )

    _sql_constraints = [
        ('name_category_uniq', 'unique(name, category)',
         "Ce type de matériau existe déjà pour cette catégorie."),
    ]

    @api.depends('product_tmpl_ids')
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = len(rec.product_tmpl_ids)

    def name_get(self):
        result = []
        category_desc = dict(
            self._fields['category'].selection
        )
        for rec in self:
            label = "%s [%s]" % (rec.name, category_desc.get(rec.category, ''))
            result.append((rec.id, label))
        return result
