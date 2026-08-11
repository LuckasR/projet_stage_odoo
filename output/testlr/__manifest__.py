{
    "name": "Construction Management",
    "summary": "Gestion des projets de construction",
    "description": """
Module de gestion de chantier permettant de gérer :
- Les projets
- Les phases
- Les tâches
- Les matériaux
- Les stocks
- Les consommations
- Les inventaires
- Les budgets
""",
    "author": "L. M. RABEMIAFARA",
    "category": "Construction",
    "version": "17.0.1.0.0",
    "license": "LGPL-3",

    "depends": [
        "base",
        "project",
    ],

    'data': [
        'security/ir.model.access.csv',
        'views/construction_file_views.xml',
        'views/menu.xml',
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}