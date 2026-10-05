# -*- coding: utf-8 -*-
from odoo import fields, models


class ConstructionMaterialCharacteristic(models.Model):
    """Une valeur concrète pour une caractéristique, sur un produit donné.
    Ex: Fer HA10 -> diameter = 10 mm, bar_length = 12 m.
    """
    _name = 'construction.material.characteristic'
    _description = "Valeur de caractéristique du matériau"
    _order = 'sequence, id'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string="Produit",
        required=True,
        ondelete='cascade',
    )
    attribute_id = fields.Many2one(
        'construction.material.attribute',
        string="Caractéristique",
        required=True,
        ondelete='restrict',
    )
    sequence = fields.Integer(related='attribute_id.sequence', store=True)
    value_type = fields.Selection(related='attribute_id.value_type')
    uom_id = fields.Many2one(related='attribute_id.uom_id')

    value_float = fields.Float(string="Valeur numérique", digits=(12, 4))
    value_char = fields.Char(string="Valeur texte")
    value_selection_id = fields.Many2one(
        'construction.material.attribute.option',
        string="Valeur (liste)",
        domain="[('attribute_id', '=', attribute_id)]",
    )

    _sql_constraints = [
        (
            'product_attribute_uniq',
            'unique(product_tmpl_id, attribute_id)',
            "Cette caractéristique existe déjà pour ce produit.",
        ),
    ]