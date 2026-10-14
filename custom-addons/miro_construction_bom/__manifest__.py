# -*- coding: utf-8 -*-
{
    'name': "Construction — Nomenclatures et besoins matériaux",
    'version': '17.0.1.1.0',
    'category': 'Services/Project',
    'summary': "Relie les métrés des éléments de construction aux nomenclatures : "
               "besoins matériaux par phase, achats et consommations.",
    'description': """
Pont entre la gestion de chantier (miro_construction_project), les
nomenclatures natives d'Odoo (mrp.bom) et les catégories de matériaux
(construction_product_management) :

* une nomenclature native par ligne de gabarit de phases (Coulage -> béton
  dosé 350), avec coefficient de pertes et catégorie de matériau par ligne,
  kits imbriqués (mortier dans la maçonnerie) ; aucun ordre de fabrication,
  surchargeable par type d'élément (semelle en C20/25, poteau en C25/30) ;
* besoins matériaux calculés par phase : métré x recette x coefficient de
  pertes, recalculés quand les métrés changent (phases non commencées) ;
* choix du produit réel par projet pour chaque besoin générique ;
* synthèse par élément, ouvrage, niveau, projet ; comparaison au stock ;
* demandes de prix fournisseurs générées depuis les besoins ;
* déclaration des consommations réelles (mouvements de stock vers le
  chantier) et écart prévu / réel.
""",
    'author': "Votre Entreprise",
    'license': 'LGPL-3',
    'depends': ['miro_construction_project', 'construction_product_management',
                'mrp', 'purchase', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'data/uom_group_data.xml',
        'data/stock_location_data.xml',
        'views/construction_material_need_views.xml',
        'views/construction_bom_link_views.xml',
        'views/project_views.xml',
        'wizard/need_purchase_wizard_views.xml',
        'wizard/need_consume_wizard_views.xml',
        'views/menu_views.xml',
        'data/default_boms.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
