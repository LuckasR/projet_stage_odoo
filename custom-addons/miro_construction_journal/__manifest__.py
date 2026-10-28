# -*- coding: utf-8 -*-
{
    'name': "Construction — Journal de chantier",
    'version': '17.0.1.3.0',
    'category': 'Services/Project',
    'summary': "Rapport journalier du chef de chantier : main-d'œuvre, matières, "
               "matériel, dépenses et quantités réalisées ; coûts réels et "
               "avancement calculés, sans saisie de montant.",
    'description': """
Un journal par chantier et par jour, rempli par le chef de chantier. Il valide
ses lignes au fil de la journée (un travail entier, ou une ligne seule) : une
ligne validée est figée et alimente aussitôt :

* le coût réel de main-d'œuvre : heures x coût horaire chargé de l'ouvrier
  (paramètres de paie de miro_hr_paie) ;
* le coût réel des matières : sortie de stock vers « Consommation chantier »,
  au coût du produit le jour de la sortie (miro_construction_bom) ;
* le coût réel du matériel : heures x taux horaire de l'engin ;
* les frais divers (transport, achats sur place...) ;
* l'avancement des phases : quantité réalisée cumulée / métré de la phase ;
* les intempéries et incidents de la journée.

On ajoute des lignes tant que le journal n'est pas validé (une phase peut
avoir plusieurs travaux dans la journée). Seul le conducteur de travaux remet
une ligne validée en brouillon (ses matières reviennent en stock) et valide
le journal entier, qui valide les lignes restantes et fige tout.

Le coût réel des tâches et du projet n'est plus saisi : il est calculé
depuis les lignes validées et les consommations.
""",
    'author': "Miro Construction",
    'license': 'LGPL-3',
    'depends': ['miro_construction_bom', 'miro_construction_planning'],
    'data': [
        'security/ir.model.access.csv',
        'views/site_equipment_views.xml',
        'views/site_journal_views.xml',
        'views/project_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
