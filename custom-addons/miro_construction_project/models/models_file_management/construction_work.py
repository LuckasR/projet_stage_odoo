import base64
import json
import logging
import tempfile

from odoo import api, fields, models

from odoo.exceptions import UserError


class ConstructionWork(models.Model):
    _name = 'construction.work'
    _description = 'Ouvrage de construction'

    # Nom du chose a creer 
    name = fields.Char(
        string='Nom',
        required=True
    )

    # code metier   
    code = fields.Char(
        string='Code'
    )

    # Type de construction 
    work_type = fields.Selection([
        # Fondations
        ('FOUNDATION', 'Fondation'),
        ('FOOTING', 'Semelle'),
        ('RAFT', 'Radier'),
        ('PILE', 'Pieu'),
        ('PILE_CAP', 'Tête de pieu'),

        # Structure
        ('COLUMN', 'Poteau'),
        ('BEAM', 'Poutre'),
        ('SLAB', 'Dalle'),
        ('WALL', 'Mur'),
        ('SHEAR_WALL', 'Voile'),

        # Escaliers
        ('STAIR', 'Escalier'),
        ('RAMP', 'Rampe'),

        # Toiture
        ('ROOF', 'Toiture'),
        ('ROOF_SLAB', 'Dalle de toiture'),

        # Ouvrages particuliers
        ('TERRACE', 'Terrasse'),
        ('BALCONY', 'Balcon'),
        ('CANOPY', 'Auvent'),

        # Ouverture / éléments
        ('DOOR', 'Porte'),
        ('WINDOW', 'Fenêtre'),

        # Extérieur
        ('RETAINING_WALL', 'Mur de soutènement'),
        ('FENCE', 'Clôture'),
        ('PAVEMENT', 'Pavage / Dallage'),
        ('DRAINAGE', 'Drainage'),

        # Autre
        ('OTHER', 'Autre'),
    ], string='Type d’ouvrage', required=True)

    project_id = fields.Many2one(
        'construction.project',
        string='Projet',
        required=True
    )

    building_id = fields.Many2one(
        'construction.building',
        string='Bâtiment'
    )

    level_id = fields.Many2one(
        'construction.level',
        string='Niveau'
    )

    zone_id = fields.Many2one(
        'construction.zone',
        string='Zone'
    )

    description = fields.Text(
        string='Description'
    )