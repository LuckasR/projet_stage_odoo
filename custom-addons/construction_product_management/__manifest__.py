# -*- coding: utf-8 -*-
{
    'name': 'Construction Product Management',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': "Gestion des produits de construction (ciment, sable, gravier, etc.)",
    'description': """
Construction Product Management
================================
Ce module étend product.template pour permettre la gestion spécifique
des matériaux de construction :
- Ciment (classe de résistance, type CPA/CPJ...)
- Sable (granulométrie, origine)
- Gravier / Gravillon (granulométrie, calibre)
- Acier / Fer à béton (diamètre, nuance)
- Bois, briques, parpaings et autres matériaux

Fonctionnalités :
- Catégorisation des matériaux de construction
- Champs techniques spécifiques (densité, granulométrie, classe...)
- Conversion / suivi en unités adaptées (sac, m3, tonne, botte...)
- Vue dédiée et filtres dans la fiche produit
    """,
    'author': 'L. M. RABEMIAFARA',
    'website': 'https://www.example.com',
    'license': 'LGPL-3',
    'depends': ['product', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'data/construction_material_type_data.xml',
        'views/product_template_views.xml',
        'views/construction_material_type_views.xml',
        'views/construction_material_attribute_views.xml',
        'views/construction_bom_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}