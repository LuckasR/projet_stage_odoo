{
    'name': 'Miro Materiaux Managements',
    'version': '17.0.1.0.0',
    'summary': 'Gestion des materiaux (extension du produit Odoo)',
    'description': '''
Ajoute des champs "materiaux" (reference Miro, notes) sur les produits
et un menu dedie pour retrouver rapidement les produits de la categorie
"Materiaux".
''',
    'author': 'L. M. Rabemiafara, Miro K.E.',
    'website': 'https://www.example.com',
    'license': 'LGPL-3',
    'category': 'Inventory',
    'depends': [
        'base',
        'product',
    ],
    'data': [
        'views/views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
