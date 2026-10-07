# -*- coding: utf-8 -*-
# Carte d'identite du module 

{
    'name': "Gestion de Projets de Construction",
    'version': '17.0.1.0.0',
    'category': 'Services/Project',
    'summary': "Extension du module Project pour le suivi de chantiers de construction "
                "(hiérarchie tâches/sous-tâches en diagramme, avancement, coûts, incidents).",
    'description': """
Gestion de Projets de Construction
===================================

Ce module étend le module Project standard d'Odoo pour répondre aux besoins
spécifiques de la gestion de chantiers de construction :

* Hérite de project.project et project.task (aucune donnée existante n'est perdue)
* Informations chantier sur le projet : adresse, type de construction, phase,
  budget, dates, maître d'ouvrage, architecte, chef de chantier
* Diagramme hiérarchique (vue "hierarchy") affichant le projet, ses tâches,
  sous-tâches et sous-sous-tâches (profondeur illimitée) avec possibilité de
  tout déplier / replier, et un pourcentage d'avancement affiché sur chaque nœud
* Avancement calculé automatiquement de bas en haut : une tâche sans enfant a un
  avancement saisi manuellement, une tâche avec enfants a la moyenne de ses enfants
* Chaque tâche/sous-tâche reste cliquable et ouvre sa fiche détaillée complète
  (quel que soit son niveau de profondeur)
* Suivi de coûts prévus / réels par tâche et consolidé par projet
* Détection automatique des tâches en retard
* Registre d'incidents de chantier par tâche (gravité, état, responsable)
* Vues liste avec code couleur (retard / terminé) et barres de progression
""",
    'author': "Votre Entreprise",
    'website': "https://www.example.com",
    'license': 'LGPL-3',
    'depends': ['project', 'mail', 'queue_job'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'data/queue_job_data.xml',
        'data/queue_job_analysis_data.xml',
        'data/construction_phase_template_data.xml',
        'data/construction_opening_data.xml',
        'data/construction_formwork_data.xml',
        'views/project_task_hierarchy_action.xml',
        'views/project_project_views_construction.xml', 
        'views/project_task_views.xml',
        'views/project_project_views.xml',
        'views/construction_task_incident_views.xml',
        'views/construction_file_views.xml',
        'views/construction_wall_views.xml',
        'views/construction_facade_views.xml',
        'views/construction_element_views.xml',
        'views/construction_opening_views.xml',
        'views/menu_views.xml',
        'data/construction_plan_type_analyzers.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'miro_construction_project/static/src/task_hierarchy/task_hierarchy.js',
            'miro_construction_project/static/src/task_hierarchy/task_hierarchy.xml',
            'miro_construction_project/static/src/task_hierarchy/task_hierarchy.scss',
            'miro_construction_project/static/src/viewer_menu/viewer_menu.js',
            'miro_construction_project/static/src/viewer_menu/viewer_menu.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
