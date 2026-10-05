{
    'name': 'Gestion des composants par niveau',
    'version': '17.0.1.0.0',
    'summary': "Suivi des composants de construction (semelles, murs, poteaux...) par niveau et par projet",
    'category': 'Construction',
    'author': 'Votre société',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/construction_composant_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
