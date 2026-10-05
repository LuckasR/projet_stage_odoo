# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProjectTask(models.Model):
    _inherit = 'project.task'
    
    sequence = fields.Integer(
        string="Séquence",
        default=10
    )
    
    # ------------------------------------------------------------------
    # Avancement (calcul récursif : mère = moyenne des filles)
    # ------------------------------------------------------------------
    x_avancement_manuel = fields.Float(
        string="Avancement manuel (%)", default=0.0,
        help="Saisi à la main pour une tâche qui n'a pas de sous-tâche. "
             "Ignoré (recalculé) dès que la tâche a des sous-tâches.")

    x_avancement_global = fields.Float(
        string="Avancement (%)",
        compute='_compute_avancement_global', store=True,
        help="Pour une tâche sans sous-tâche : recopie l'avancement manuel.\n"
             "Pour une tâche avec sous-tâches : moyenne de l'avancement de ses "
             "sous-tâches directes (donc, en cascade, de tous ses descendants).")

    x_niveau_hierarchie = fields.Integer(
        compute='_compute_niveau', store=True,
        string="Niveau", help="0 = tâche racine du projet, 1 = sous-tâche, 2 = sous-sous-tâche, ...")

    x_sous_taches_count_total = fields.Integer(
        compute='_compute_sous_taches_total',
        string="Sous-tâches (tous niveaux confondus)")

    # ------------------------------------------------------------------
    # Planification / coûts / corps de métier
    # ------------------------------------------------------------------
    x_date_debut_prevue = fields.Date(string="Début prévu")
    x_date_fin_prevue = fields.Date(string="Fin prévue")
    x_duree_prevue_jours = fields.Float(string="Durée prévue (jours)")
    currency_id = fields.Many2one(
        'res.currency',
        string='Devise',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    x_cout_prevue = fields.Monetary(string="Coût prévu", currency_field='currency_id')
    x_cout_reel = fields.Monetary(string="Coût réel", currency_field='currency_id')

    x_responsable_technique_id = fields.Many2one(
        'res.users', string="Responsable technique")

    x_corps_metier = fields.Selection([
        ('gros_oeuvre', 'Gros œuvre'),
        ('plomberie', 'Plomberie'),
        ('electricite', 'Électricité'),
        ('menuiserie', 'Menuiserie'),
        ('peinture', 'Peinture'),
        ('carrelage', 'Carrelage / Revêtement'),
        ('toiture', 'Toiture / Charpente'),
        ('vrd', 'VRD / Terrassement'),
        ('autre', 'Autre'),
    ], string="Corps de métier")

    x_niveau_priorite_chantier = fields.Selection([
        ('normal', 'Normal'),
        ('urgent', 'Urgent'),
        ('bloquant', 'Bloquant'),
    ], string="Priorité chantier", default='normal')

    x_est_en_retard = fields.Boolean(
        compute='_compute_est_en_retard', store=True, string="En retard")

    # ------------------------------------------------------------------
    # Incidents de chantier
    # ------------------------------------------------------------------
    x_incident_ids = fields.One2many(
        'construction.task.incident', 'task_id', string="Incidents / Problèmes")
    x_incident_count = fields.Integer(
        compute='_compute_incident_count', string="Nb incidents")

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('child_ids.x_avancement_global', 'child_ids', 'x_avancement_manuel')
    def _compute_avancement_global(self):
        # On traite d'abord les feuilles profondes puis on remonte : Odoo gère
        # l'ordre de calcul grâce au graphe de dépendances (child -> parent).
        for task in self:
            if task.child_ids:
                children = task.child_ids
                task.x_avancement_global = sum(
                    children.mapped('x_avancement_global')) / len(children)
            else:
                task.x_avancement_global = task.x_avancement_manuel

    @api.depends('parent_id', 'parent_id.x_niveau_hierarchie')
    def _compute_niveau(self):
        for task in self:
            level = 0
            parent = task.parent_id
            # Sécurité anti-boucle infinie (ne devrait jamais arriver)
            seen = set()
            while parent and parent.id not in seen:
                seen.add(parent.id)
                level += 1
                parent = parent.parent_id
            task.x_niveau_hierarchie = level

    def _compute_sous_taches_total(self):
        for task in self:
            task.x_sous_taches_count_total = len(task._get_all_descendants())

    def _get_all_descendants(self):
        """Retourne l'ensemble des descendants (filles, petites-filles, ...)."""
        self.ensure_one()
        descendants = self.env['project.task']
        to_explore = self.child_ids
        while to_explore:
            descendants |= to_explore
            to_explore = to_explore.mapped('child_ids') - descendants

        return descendants

    @api.depends('date_deadline', 'x_avancement_global')
    def _compute_est_en_retard(self):
        now = fields.Datetime.now()

        for task in self:
            task.x_est_en_retard = bool(
                task.date_deadline
                and task.date_deadline < now
                and task.x_avancement_global < 100
            )

    def _compute_incident_count(self):
        for task in self:
            task.x_incident_count = len(task.x_incident_ids)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_view_hierarchy_from_task(self):
        """Ouvre le diagramme hiérarchique complet du projet, en gardant le
        contexte de la tâche courante (utile depuis la fiche d'une sous-tâche)."""
        self.ensure_one()
        action = self.env['ir.actions.client']._for_xml_id(
            'miro_construction_project.action_project_task_hierarchy')
        action['context'] = {'default_project_id': self.project_id.id}
        return action

    def action_open_incidents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Incidents - %s" % self.name,
            'res_model': 'construction.task.incident',
            'view_mode': 'list,form',
            'domain': [('task_id', '=', self.id)],
            'context': {'default_task_id': self.id},
        }

    def action_view_children_tasks(self):
        """Ouvre la liste des sous-tâches directes (bouton depuis le diagramme
        ou la fiche tâche)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Sous-tâches de %s" % self.name,
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('parent_id', '=', self.id)],
            'context': {
                'default_parent_id': self.id,
                'default_project_id': self.project_id.id,
            },
        }
