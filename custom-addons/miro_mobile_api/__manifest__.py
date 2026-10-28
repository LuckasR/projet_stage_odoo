# -*- coding: utf-8 -*-
{
    'name': "Construction — API mobile",
    'version': '17.0.1.1.0',
    'category': 'Services/Project',
    'summary': "API REST de l'application mobile SuiviChantier : journal de "
               "chantier, avancement des phases, incidents et photos, hors-ligne.",
    'description': """
API de l'application mobile du chef de chantier (SuiviChantier).

* Connexion par jeton longue durée, un par appareil, révocable depuis Odoo ;
* ``GET  /api/mobile/v1/sync/pull`` : instantané des chantiers de l'utilisateur
  (phases, besoins matière, ouvriers, matériel, journaux récents, incidents) ;
* ``POST /api/mobile/v1/sync/push`` : file d'opérations saisies hors-ligne (en-tête du journal, travaux ligne à ligne, incidents),
  chacune identifiée par un uuid (rejouable sans doublon). Une modification
  faite au bureau entre-temps est signalée comme conflit, jamais écrasée ;
* ``POST /api/mobile/v1/photos`` : photos du journal ou d'un incident.

Le chef de chantier valide les lignes depuis l'application ; la validation du
journal entier reste au conducteur de travaux, dans Odoo.
""",
    'author': "Miro Construction",
    'license': 'LGPL-3',
    'depends': ['miro_construction_journal', 'miro_construction_project'],
    'data': [
        'security/ir.model.access.csv',
        'views/mobile_device_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
