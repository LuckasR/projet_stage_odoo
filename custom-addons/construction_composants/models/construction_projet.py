# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ConstructionProjet(models.Model):
    _name = 'construction.projet'
    _description = "Projet de construction"

    name = fields.Char(string="Nom du projet", required=True)
    active = fields.Boolean(default=True)

    niveau_ids = fields.One2many(
        'construction.niveau', 'projet_id', string="Niveaux"
    )
    niveau_count = fields.Integer(
        string="Nb niveaux", compute='_compute_counts'
    )
    composant_count = fields.Integer(
        string="Nb composants", compute='_compute_counts'
    )

    @api.depends('niveau_ids', 'niveau_ids.composant_ids')
    def _compute_counts(self):
        for rec in self:
            rec.niveau_count = len(rec.niveau_ids)
            rec.composant_count = sum(rec.niveau_ids.mapped('composant_count'))
