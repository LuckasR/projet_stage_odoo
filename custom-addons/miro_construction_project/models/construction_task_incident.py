# -*- coding: utf-8 -*-
from odoo import models, fields


class ConstructionTaskIncident(models.Model):
    _name = 'construction.task.incident'
    _description = "Incident / Problème de chantier"
    _order = 'date_incident desc, id desc'

    task_id = fields.Many2one(
        'project.task', string="Tâche", required=True, ondelete='cascade')
    project_id = fields.Many2one(
        related='task_id.project_id', string="Projet", store=True)

    name = fields.Char(string="Titre", required=True)
    description = fields.Text(string="Description")
    date_incident = fields.Date(string="Date", default=fields.Date.context_today)

    gravite = fields.Selection([
        ('faible', 'Faible'),
        ('moyenne', 'Moyenne'),
        ('haute', 'Haute'),
        ('critique', 'Critique'),
    ], string="Gravité", default='moyenne', required=True)

    etat = fields.Selection([
        ('ouvert', 'Ouvert'),
        ('en_cours', 'En cours de résolution'),
        ('resolu', 'Résolu'),
    ], string="État", default='ouvert', required=True)

    responsable_id = fields.Many2one('res.users', string="Assigné à")
