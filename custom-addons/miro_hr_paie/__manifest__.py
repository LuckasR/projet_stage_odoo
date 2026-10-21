# -*- coding: utf-8 -*-
{
    'name': "Miro Construction — Présences et paie",
    'version': '17.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': "Paie des ouvriers à la journée, à l'heure ou au mois, calculée "
               "depuis les présences ; bulletin de paie PDF Miro Construction.",
    'description': """
Paie simple pour le chantier, au-dessus des présences d'Odoo (hr_attendance) :

* mode de paie par employé : journalier, horaire ou mensuel, avec son taux ;
* heures supplémentaires au-delà de la journée normale, avec majoration ;
* absences non rémunérées déduites pour les mensuels (paramétrable) ;
* cotisations salariales et patronales (CNaPS, organisme de santé) et
  IRSA par tranches, paramétrables (Paramètres > Employés > Paie) ;
* primes, indemnités et avances saisies à la main sur le bulletin ;
* génération des bulletins d'une période pour tous les employés ;
* bulletin de paie PDF à la mise en page Miro Construction.

Odoo Community ne propose pas de module de paie : celui-ci en est une
version volontairement simple, à faire valider par le service comptable
(taux et barèmes livrés à titre indicatif).
""",
    'author': "Miro Construction",
    'license': 'LGPL-3',
    'depends': ['hr', 'hr_attendance', 'miro_report_layout'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/irsa_bracket_data.xml',
        'views/hr_employee_views.xml',
        'views/payslip_views.xml',
        'views/irsa_bracket_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/payslip_generate_views.xml',
        'report/payslip_report.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'miro_hr_paie/static/src/scss/payslip_report.scss',
        ],
    },
    'installable': True,
    'application': False,
}
