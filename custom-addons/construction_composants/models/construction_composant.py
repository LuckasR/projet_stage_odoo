# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ConstructionComposant(models.Model):
    _name = 'construction.composant'
    _description = "Composant de construction (semelle, mur, poteau...)"

    name = fields.Char(string="Référence", required=True)
    niveau_id = fields.Many2one(
        'construction.niveau', string="Niveau",
        required=True, ondelete='cascade'
    )
    projet_id = fields.Many2one(
        related='niveau_id.projet_id', string="Projet",
        store=True, readonly=True
    )
    type_id = fields.Many2one(
        'construction.type.composant', string="Type",
        required=True
    )
    gere_les_faces = fields.Boolean(
        related='type_id.gere_les_faces', string="Gère les faces"
    )
    quantite = fields.Integer(string="Quantité", default=1)

    dimension_ids = fields.One2many(
        'construction.composant.dimension', 'composant_id',
        string="Dimensions"
    )
    face_ids = fields.One2many(
        'construction.composant.face', 'composant_id', string="Faces"
    )

    _sql_constraints = [
        ('quantite_positive', 'CHECK(quantite > 0)',
         "La quantité doit être positive."),
    ]

    @api.onchange('type_id')
    def _onchange_type_id(self):
        """Pré-remplit les lignes de dimension à partir du type choisi."""
        if self.type_id:
            lines = [(5, 0, 0)]
            for attr in self.type_id.attribut_ids:
                lines.append((0, 0, {
                    'name': attr.name,
                    'unite': attr.unite,
                }))
            self.dimension_ids = lines


class ConstructionComposantDimension(models.Model):
    _name = 'construction.composant.dimension'
    _description = "Dimension d'un composant"
    _order = 'sequence, id'

    composant_id = fields.Many2one(
        'construction.composant', required=True, ondelete='cascade'
    )
    name = fields.Char(
        string="Attribut", required=True,
        help="Ex : longueur, largeur, hauteur, épaisseur"
    )
    valeur = fields.Float(string="Valeur", required=True)
    unite = fields.Selection([
        ('m', 'Mètre'),
        ('cm', 'Centimètre'),
        ('mm', 'Millimètre'),
    ], string="Unité", default='m', required=True)
    sequence = fields.Integer(default=10)


class ConstructionComposantFace(models.Model):
    _name = 'construction.composant.face'
    _description = "Face d'un composant (ex : mur)"

    composant_id = fields.Many2one(
        'construction.composant', required=True, ondelete='cascade'
    )
    orientation = fields.Selection([
        ('nord', 'Nord'),
        ('sud', 'Sud'),
        ('est', 'Est'),
        ('ouest', 'Ouest'),
    ], string="Orientation", required=True)
    type_face = fields.Selection([
        ('interieure', 'Intérieure'),
        ('exterieure', 'Extérieure'),
    ], string="Type de face", required=True)
    longueur = fields.Float(string="Longueur (m)")
    hauteur = fields.Float(string="Hauteur (m)")
