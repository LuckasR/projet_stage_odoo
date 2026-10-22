# -*- coding: utf-8 -*-
{
    'name': "Construction — Vue d'ensemble du chantier",
    'version': '17.0.1.0.0',
    'category': 'Services/Project',
    'summary': "Fiche chantier complète : indicateurs, alertes, avancement par "
               "ouvrage, coûts prévus / réels, matériaux, activité et incidents.",
    'description': """
Premier onglet de la fiche chantier, calculé à l'ouverture depuis les autres
modules Miro Construction (aucune saisie) :

* indicateurs : avancement réel et attendu à date, délai, budget consommé,
  dérive des coûts et coût final estimé, heures réalisées / prévues ;
* alertes : retards, incidents ouverts, journaux à valider, stock
  insuffisant, surconsommation, données de chiffrage manquantes ;
* avancement et coût réel par ouvrage ;
* coûts prévus / réels par nature (main-d'œuvre, matières, matériel, frais) ;
* approvisionnement des matériaux ;
* derniers journaux de chantier et incidents ouverts ;
* accès directs : journal du jour, maquette 3D, matériaux, incidents, éléments.
""",
    'author': "Miro Construction",
    'license': 'LGPL-3',
    'depends': ['miro_construction_journal'],
    'data': [
        'views/overview_templates.xml',
        'views/project_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'miro_construction_overview/static/src/scss/overview.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': True,
}
