# -*- coding: utf-8 -*-
{
    'name': "Construction — Équipes, cadences et main-d'œuvre",
    'version': '17.0.1.0.0',
    'category': 'Services/Project',
    'summary': "Métiers, équipes types et cadences : durée, effectif et coût de "
               "main-d'œuvre de chaque phase, base du planning.",
    'description': """
Étape 1 de la planification des chantiers :

* métiers (maçon, coffreur, ferrailleur, manœuvre...) : coût horaire chargé
  et effectif disponible calculés depuis les employés (miro_hr_paie) ;
* équipes types : composition (1 maçon + 1 manœuvre...) et coût horaire ;
* cadences : quantité produite par heure, pour un type de phase et une
  équipe, éventuellement propre à un type d'élément ;
* délais techniques entre phases (décoffrage 7 jours après le coulage...) ;
* pour chaque phase : équipe retenue, effectif, durée et coût de
  main-d'œuvre ; synthèse par métier sur le projet.
""",
    'author': "Miro Construction",
    'license': 'LGPL-3',
    'depends': ['miro_construction_project', 'miro_hr_paie', 'resource', 'miro_gantt_view'],
    'data': [
        'security/ir.model.access.csv',
        'data/trade_data.xml',
        'views/trade_views.xml',
        'views/crew_views.xml',
        'views/crew_rate_views.xml',
        'views/hr_employee_views.xml',
        'views/phase_template_views.xml',
        'views/project_views.xml',
        'views/planning_views.xml',
        'views/menu_views.xml',
        'data/default_crews.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'miro_construction_planning/static/src/gantt/gantt_initial_date.js',
        ],
    },
    'installable': True,
    'application': False,
}
