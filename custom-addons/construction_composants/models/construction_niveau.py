# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ConstructionNiveau(models.Model):
    _name = 'construction.niveau'
    _description = "Niveau du bâtiment (Fondation, R+0, R+1...)"
    _order = 'sequence, id'

    name = fields.Char(
        string="Nom", required=True,
        help="Ex : Fondation, R+0, R+1, R+2..."
    )
    sequence = fields.Integer(string="Ordre", default=10)
    projet_id = fields.Many2one(
        'construction.projet', string="Projet",
        required=True, ondelete='cascade'
    )

    composant_ids = fields.One2many(
        'construction.composant', 'niveau_id', string="Composants"
    )
    composant_count = fields.Integer(
        string="Nb composants", compute='_compute_composant_count'
    )

    @api.depends('composant_ids')
    def _compute_composant_count(self):
        for rec in self:
            rec.composant_count = len(rec.composant_ids)

    _sql_constraints = [
        ('name_projet_uniq', 'unique(name, projet_id)',
         "Ce niveau existe déjà pour ce projet."),
    ]
