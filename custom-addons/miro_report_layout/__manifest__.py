# -*- coding: utf-8 -*-
{
    'name': "Miro Construction — Mise en page des documents",
    'version': '17.0.1.0.0',
    'category': 'Hidden/Tools',
    'summary': "Mise en page professionnelle Miro Construction pour tous les PDF "
               "(factures, bons de commande, bons de livraison...).",
    'description': """
Mise en page « Miro Construction » :

* en-tête de marque (logo, ou nom de l'entreprise en lettrage si aucun logo)
  et coordonnées ; pied de page avec les mentions légales malgaches
  (NIF, STAT, RCS), les contacts et la pagination ;
* tableaux, blocs d'informations et totaux habillés aux couleurs de la
  société (Paramètres > Configurer la mise en page des documents) ;
* facture : coordonnées bancaires, montant en toutes lettres
  (« Arrêtée la présente facture à la somme de ... ») et zone
  « Cachet et signature ».

La mise en page s'applique à TOUS les documents PDF qui utilisent la mise
en page externe d'Odoo. Elle reste sélectionnable comme les mises en page
natives (Light, Boxed, Bold, Striped).
""",
    'author': "Miro Construction",
    'license': 'LGPL-3',
    'depends': ['web', 'account'],
    'data': [
        'views/report_layout_templates.xml',
        'views/report_invoice_templates.xml',
        'views/res_company_views.xml',
        'data/report_layout_data.xml',
        'data/company_branding.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'miro_report_layout/static/src/scss/report_miro.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
