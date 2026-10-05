# # -*- coding: utf-8 -*-
# from odoo import models, fields, api


# class ProjectProject(models.Model):
#     _inherit = 'project.project'

#     # ------------------------------------------------------------------
#     # Informations chantier
#     # ------------------------------------------------------------------
#     x_type_construction = fields.Selection([
#         ('residentiel', 'Résidentiel'),
#         ('commercial', 'Commercial'),
#         ('industriel', 'Industriel'),
#         ('infrastructure', 'Infrastructure'),
#         ('renovation', 'Rénovation'),
#     ], string="Type de construction", tracking=True)

#     x_phase_projet = fields.Selection([
#         ('etude', 'Étude & conception'),
#         ('permis', 'Permis & autorisations'),
#         ('terrassement', 'Terrassement'),
#         ('gros_oeuvre', 'Gros œuvre'),
#         ('second_oeuvre', 'Second œuvre'),
#         ('finition', 'Finitions'),
#         ('livraison', 'Réception & livraison'),
#     ], string="Phase actuelle", default='etude', tracking=True)

#     x_adresse_chantier = fields.Char(string="Adresse du chantier")
#     x_ville_chantier = fields.Char(string="Ville")
#     x_surface_totale = fields.Float(string="Surface totale (m²)")
#     x_date_debut_travaux = fields.Date(string="Début des travaux")
#     x_date_fin_prevue = fields.Date(string="Fin prévue")
#     x_maitre_ouvrage = fields.Char(string="Maître d'ouvrage")
#     x_architecte = fields.Char(string="Architecte / Bureau d'études")
#     x_responsable_chantier_id = fields.Many2one(
#         'res.users', string="Chef de chantier")

#     # ------------------------------------------------------------------
#     # Budget / coûts (consolidés depuis les tâches)
#     # ------------------------------------------------------------------
#     x_budget_total = fields.Monetary(
#         string="Budget prévu", currency_field='currency_id')
#     x_cout_reel_total = fields.Monetary(
#         string="Coût réel total", currency_field='currency_id',
#         compute='_compute_couts', store=True)
#     x_cout_prevue_total = fields.Monetary(
#         string="Coût prévu total (tâches)", currency_field='currency_id',
#         compute='_compute_couts', store=True)

#     # ------------------------------------------------------------------
#     # Avancement global (moyenne des tâches racines du projet)
#     # ------------------------------------------------------------------
#     x_avancement_global = fields.Float(
#         string="Avancement global (%)",
#         compute='_compute_avancement_global', store=True)

#     x_task_count_all = fields.Integer(
#         compute='_compute_task_counts', string="Nb tâches (total, avec sous-tâches)" , store=True)
#     x_task_en_retard_count = fields.Integer(
#         compute='_compute_task_counts', string="Tâches en retard" , store=True) 

#     x_status = fields.Selection([
#         ('nouveau',      'Nouveau'),
#         ('en_cours',     'En cours'),
#         ('en_pause',     'En pause'),
#         ('termine',      'Terminé'),
#         ('annule',       'Annulé'),
#     ], string="Statut", default='nouveau', tracking=True, required=True)

#     x_status_color = fields.Integer(
#         compute='_compute_status_color', string="Couleur statut")

#     @api.depends('x_status')
#     def _compute_status_color(self):
#         mapping = {
#             'nouveau':  0,   # gris
#             'en_cours': 1,   # bleu
#             'en_pause': 2,   # orange
#             'termine':  3,   # vert
#             'annule':   4,   # rouge
#         }
#         for project in self:
#             project.x_status_color = mapping.get(project.x_status, 0)
            
#     @api.depends('x_avancement_global')
#     def _compute_status_from_avancement(self):
#         for project in self:
#             if project.x_status == 'annule':
#                 continue
#             if project.x_avancement_global >= 100:
#                 project.x_status = 'termine'
#             elif project.x_avancement_global > 0:
#                 project.x_status = 'en_cours'     
                
                   
#     @api.depends('tasks.x_avancement_global', 'tasks.parent_id')
#     def _compute_avancement_global(self):
#         for project in self:
#             root_tasks = project.tasks.filtered(lambda t: not t.parent_id)
#             if root_tasks:
#                 project.x_avancement_global = sum(
#                     root_tasks.mapped('x_avancement_global')) / len(root_tasks)
#             else:
#                 project.x_avancement_global = 0.0

#     @api.depends('tasks.x_cout_reel', 'tasks.x_cout_prevue')
#     def _compute_couts(self):
#         for project in self:
#             project.x_cout_reel_total = sum(project.tasks.mapped('x_cout_reel'))
#             project.x_cout_prevue_total = sum(project.tasks.mapped('x_cout_prevue'))

#     def _compute_task_counts(self):
#         for project in self:
#             all_tasks = project.tasks
#             project.x_task_count_all = len(all_tasks)
#             project.x_task_en_retard_count = len(all_tasks.filtered('x_est_en_retard'))

#     # ------------------------------------------------------------------
#     # Actions
#     # ------------------------------------------------------------------
#     def action_view_task_hierarchy(self):
#         """Ouvre le diagramme hiérarchique (mère/fille) des tâches du projet."""
#         self.ensure_one()
#         action = self.env['ir.actions.client']._for_xml_id(
#             'miro_construction_project.action_project_task_hierarchy')
#         action['name'] = "Diagramme des tâches - %s" % self.name
#         action['context'] = {'default_project_id': self.id}
#         return action

#     def action_view_tasks_flat(self):
#         """Ouvre la liste plate de toutes les tâches/sous-tâches du projet."""
#         self.ensure_one()
#         action = self.env['ir.actions.act_window']._for_xml_id(
#             'miro_construction_project.action_project_task_list_construction')
#         action['domain'] = [('project_id', '=', self.id)]
#         action['context'] = {'default_project_id': self.id}
#         return action
# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # ------------------------------------------------------------------
    # Identification chantier
    # ------------------------------------------------------------------
    construction_code = fields.Char(string="Code chantier")

    x_type_projet = fields.Selection([
        ('batiment', 'Projet bâtiment'),
        ('industriel', 'Industrielle'),
    ], string="Type de projet", tracking=True)

    # ------------------------------------------------------------------
    # Informations chantier
    # ------------------------------------------------------------------
    x_type_construction = fields.Selection([
        ('residentiel', 'Résidentiel'),
        ('commercial', 'Commercial'),
        ('industriel', 'Industriel'),
        ('infrastructure', 'Infrastructure'),
        ('renovation', 'Rénovation'),
    ], string="Type de construction", tracking=True)

    x_phase_projet = fields.Selection([
        ('etude', 'Étude & conception'),
        ('permis', 'Permis & autorisations'),
        ('terrassement', 'Terrassement'),
        ('gros_oeuvre', 'Gros œuvre'),
        ('second_oeuvre', 'Second œuvre'),
        ('finition', 'Finitions'),
        ('livraison', 'Réception & livraison'),
    ], string="Phase actuelle", default='etude', tracking=True)

    site_address = fields.Char(string="Adresse")                     # ex x_adresse_chantier
    x_adresse_chantier = fields.Char(string="Adresse du chantier")
    x_ville_chantier = fields.Char(string="Ville")
    x_surface_totale = fields.Float(string="Surface totale (m²)")
    x_date_debut_travaux = fields.Date(string="Début des travaux")
    x_date_fin_prevue = fields.Date(string="Fin prévue")
    x_maitre_ouvrage = fields.Char(string="Maître d'ouvrage")
    x_architecte = fields.Char(string="Architecte / Bureau d'études")
    x_responsable_chantier_id = fields.Many2one(
        'res.users', string="Chef de chantier")

    # ------------------------------------------------------------------
    # Statut global
    # ------------------------------------------------------------------
    x_status = fields.Selection([
        ('nouveau',  'Nouveau'),
        ('en_cours', 'En cours'),
        ('en_pause', 'En pause'),
        ('termine',  'Terminé'),
        ('annule',   'Annulé'),
    ], string="Statut", default='nouveau', tracking=True, required=True)

    x_status_color = fields.Integer(
        compute='_compute_status_color', string="Couleur statut")

    @api.depends('x_status')
    def _compute_status_color(self):
        mapping = {
            'nouveau':  0,   # gris
            'en_cours': 1,   # bleu
            'en_pause': 2,   # orange
            'termine':  3,   # vert
            'annule':   4,   # rouge
        }
        for project in self:
            project.x_status_color = mapping.get(project.x_status, 0)

    # ------------------------------------------------------------------
    # Fichiers DWG / DXF (plans)
    # ------------------------------------------------------------------
    dxf_file_ids = fields.One2many(
        'construction.dwg.files',
        'project_id',
        string="Fichiers DWG/DXF",
    )

    dxf_file_count = fields.Integer(
        string="Nb plans DWG/DXF",
        compute='_compute_dxf_file_count',
    )

    dxf_wall_detection_pending_count = fields.Integer(
        string="Détections de murs en cours",
        compute='_compute_dxf_file_count',
    )

    # ------------------------------------------------------------------
    # Budget / coûts (consolidés depuis les tâches)
    # ------------------------------------------------------------------
    x_budget_total = fields.Monetary(
        string="Budget prévu", currency_field='currency_id')
    x_cout_reel_total = fields.Monetary(
        string="Coût réel total", currency_field='currency_id',
        compute='_compute_couts', store=True)
    x_cout_prevue_total = fields.Monetary(
        string="Coût prévu total (tâches)", currency_field='currency_id',
        compute='_compute_couts', store=True)

    # ------------------------------------------------------------------
    # Avancement global (moyenne des tâches racines du projet)
    # ------------------------------------------------------------------
    x_avancement_global = fields.Float(
        string="Avancement global (%)",
        compute='_compute_avancement_global', store=True)

    x_task_count_all = fields.Integer(
        compute='_compute_task_counts', store=True,
        string="Nb tâches (total, avec sous-tâches)")
    x_task_en_retard_count = fields.Integer(
        compute='_compute_task_counts', store=True,
        string="Tâches en retard")

    # ------------------------------------------------------------------
    # Compute : avancement global
    # ------------------------------------------------------------------
    @api.depends('tasks.x_avancement_global', 'tasks.parent_id')
    def _compute_avancement_global(self):
        for project in self:
            root_tasks = project.tasks.filtered(lambda t: not t.parent_id)
            if root_tasks:
                project.x_avancement_global = sum(
                    root_tasks.mapped('x_avancement_global')) / len(root_tasks)
            else:
                project.x_avancement_global = 0.0

    # ------------------------------------------------------------------
    # Compute : fichiers DWG/DXF
    # ------------------------------------------------------------------
    @api.depends('dxf_file_ids', 'dxf_file_ids.wall_detection_state')
    def _compute_dxf_file_count(self):
        for project in self:
            project.dxf_file_count = len(project.dxf_file_ids)
            project.dxf_wall_detection_pending_count = len(
                project.dxf_file_ids.filtered(
                    lambda f: f.wall_detection_state in ('queued', 'in_progress')
                )
            )

    # ------------------------------------------------------------------
    # Compute : coûts consolidés
    # ------------------------------------------------------------------
    @api.depends('tasks.x_cout_reel', 'tasks.x_cout_prevue')
    def _compute_couts(self):
        for project in self:
            project.x_cout_reel_total = sum(project.tasks.mapped('x_cout_reel'))
            project.x_cout_prevue_total = sum(project.tasks.mapped('x_cout_prevue'))

    # ------------------------------------------------------------------
    # Compute : compteurs de tâches
    # ⚠️ avec store=True → @api.depends OBLIGATOIRE
    # ------------------------------------------------------------------
    @api.depends('tasks', 'tasks.parent_id', 'tasks.x_est_en_retard')
    def _compute_task_counts(self):
        for project in self:
            all_tasks = project.tasks
            project.x_task_count_all = len(all_tasks)
            project.x_task_en_retard_count = len(
                all_tasks.filtered('x_est_en_retard'))

    # ------------------------------------------------------------------
    # Onchange : synchroniser le statut avec l'avancement
    # (onchange = saisie manuelle, ne se déclenche pas en base)
    # ------------------------------------------------------------------
    @api.onchange('x_avancement_global')
    def _onchange_avancement_status(self):
        for project in self:
            if project.x_status == 'annule':
                continue
            if project.x_avancement_global >= 100:
                project.x_status = 'termine'
            elif project.x_avancement_global > 0:
                project.x_status = 'en_cours'

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_view_task_hierarchy(self):
        """Ouvre le diagramme hiérarchique (mère/fille) des tâches du projet."""
        self.ensure_one()
        action = self.env['ir.actions.client']._for_xml_id(
            'miro_construction_project.action_project_task_hierarchy')
        action['name'] = "Diagramme des tâches - %s" % self.name
        action['context'] = {'default_project_id': self.id}
        return action

    def action_view_tasks_flat(self):
        """Ouvre la liste plate de toutes les tâches/sous-tâches du projet."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'miro_construction_project.action_project_task_list_construction')
        action['domain'] = [('project_id', '=', self.id)]
        action['context'] = {'default_project_id': self.id}
        return action

    def action_view_dwg_files(self):
        """Ouvre la liste des plans DWG/DXF rattachés à ce projet."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'miro_construction_project.action_construction_dwg_files')
        action['name'] = "Plans DWG/DXF - %s" % self.name
        action['domain'] = [('project_id', '=', self.id)]
        action['context'] = {'default_project_id': self.id}
        return action
    
    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)

        for project in projects:
            project._create_default_construction_tasks_simple()


        return projects

    def _create_default_construction_tasks(self):
        """
        Crée automatiquement la structure complète des tâches
        de construction pour chaque projet.

        Structure :
            Étude & conception
            ├── Analyse du plan
            ├── Métré
            └── Validation des plans

            Terrassement
            ├── Implantation
            ├── Décapage
            └── Fouilles

            Gros œuvre
            ├── Fondations
            ├── Poteaux
            ├── Poutres
            ├── Dalle
            └── Escalier

            Second œuvre
            ├── Maçonnerie
            ├── Électricité
            └── Plomberie

            Finitions
            ├── Enduit
            ├── Peinture
            └── Revêtement

            Réception & livraison
            ├── Contrôle final
            └── Réception du chantier
        """
        ProjectTask = self.env['project.task']

        for project in self:

            # ==========================================================
            # 1. ÉTUDE & CONCEPTION
            # ==========================================================

            etude = ProjectTask.create({
                'name': 'Étude & conception',
                'project_id': project.id,
                'sequence': 10,
            })

            ProjectTask.create([
                {
                    'name': 'Analyse du plan',
                    'project_id': project.id,
                    'parent_id': etude.id,
                    'sequence': 10,
                },
                {
                    'name': 'Métré',
                    'project_id': project.id,
                    'parent_id': etude.id,
                    'sequence': 20,
                },
                {
                    'name': 'Validation des plans',
                    'project_id': project.id,
                    'parent_id': etude.id,
                    'sequence': 30,
                },
            ])

            # ==========================================================
            # 2. TERRASSEMENT
            # ==========================================================

            terrassement = ProjectTask.create({
                'name': 'Terrassement',
                'project_id': project.id,
                'sequence': 20,
            })

            ProjectTask.create([
                {
                    'name': 'Implantation',
                    'project_id': project.id,
                    'parent_id': terrassement.id,
                    'sequence': 10,
                },
                {
                    'name': 'Décapage',
                    'project_id': project.id,
                    'parent_id': terrassement.id,
                    'sequence': 20,
                },
                {
                    'name': 'Fouilles',
                    'project_id': project.id,
                    'parent_id': terrassement.id,
                    'sequence': 30,
                },
            ])

            # ==========================================================
            # 3. GROS ŒUVRE
            # ==========================================================

            gros_oeuvre = ProjectTask.create({
                'name': 'Gros œuvre',
                'project_id': project.id,
                'sequence': 30,
            })

            ProjectTask.create([
                {
                    'name': 'Fondations',
                    'project_id': project.id,
                    'parent_id': gros_oeuvre.id,
                    'sequence': 10,
                },
                {
                    'name': 'Poteaux',
                    'project_id': project.id,
                    'parent_id': gros_oeuvre.id,
                    'sequence': 20,
                },
                {
                    'name': 'Poutres',
                    'project_id': project.id,
                    'parent_id': gros_oeuvre.id,
                    'sequence': 30,
                },
                {
                    'name': 'Dalle',
                    'project_id': project.id,
                    'parent_id': gros_oeuvre.id,
                    'sequence': 40,
                },
                {
                    'name': 'Escalier',
                    'project_id': project.id,
                    'parent_id': gros_oeuvre.id,
                    'sequence': 50,
                },
            ])

            # ==========================================================
            # 4. SECOND ŒUVRE
            # ==========================================================

            second_oeuvre = ProjectTask.create({
                'name': 'Second œuvre',
                'project_id': project.id,
                'sequence': 40,
            })

            ProjectTask.create([
                {
                    'name': 'Maçonnerie',
                    'project_id': project.id,
                    'parent_id': second_oeuvre.id,
                    'sequence': 10,
                },
                {
                    'name': 'Électricité',
                    'project_id': project.id,
                    'parent_id': second_oeuvre.id,
                    'sequence': 20,
                },
                {
                    'name': 'Plomberie',
                    'project_id': project.id,
                    'parent_id': second_oeuvre.id,
                    'sequence': 30,
                },
            ])

            # ==========================================================
            # 5. FINITIONS
            # ==========================================================

            finition = ProjectTask.create({
                'name': 'Finitions',
                'project_id': project.id,
                'sequence': 50,
            })

            ProjectTask.create([
                {
                    'name': 'Enduit',
                    'project_id': project.id,
                    'parent_id': finition.id,
                    'sequence': 10,
                },
                {
                    'name': 'Peinture',
                    'project_id': project.id,
                    'parent_id': finition.id,
                    'sequence': 20,
                },
                {
                    'name': 'Revêtement',
                    'project_id': project.id,
                    'parent_id': finition.id,
                    'sequence': 30,
                },
            ])

            # ==========================================================
            # 6. RÉCEPTION & LIVRAISON
            # ==========================================================

            livraison = ProjectTask.create({
                'name': 'Réception & livraison',
                'project_id': project.id,
                'sequence': 60,
            })

            ProjectTask.create([
                {
                    'name': 'Contrôle final',
                    'project_id': project.id,
                    'parent_id': livraison.id,
                    'sequence': 10,
                },
                {
                    'name': 'Réception du chantier',
                    'project_id': project.id,
                    'parent_id': livraison.id,
                    'sequence': 20,
                },
            ])

        return True

    def _create_default_construction_tasks_simple(self):
        """
        Crée uniquement les tâches principales du chantier.
        """
        ProjectTask = self.env['project.task']

        for project in self:
            ProjectTask.create([
                {
                    'name': 'Étude & conception',
                    'project_id': project.id,
                    'sequence': 10,
                },
                {
                    'name': 'Terrassement',
                    'project_id': project.id,
                    'sequence': 20,
                },
                {
                    'name': 'Gros œuvre',
                    'project_id': project.id,
                    'sequence': 30,
                },
                {
                    'name': 'Second œuvre',
                    'project_id': project.id,
                    'sequence': 40,
                },
                {
                    'name': 'Finitions',
                    'project_id': project.id,
                    'sequence': 50,
                },
                {
                    'name': 'Réception & livraison',
                    'project_id': project.id,
                    'sequence': 60,
                },
            ])

        return True