{
    'name': 'Personnalisation PDF Facture',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Personnalisation du design des factures PDF',
    'depends': ['account'],  # ou 'sale' pour les devis
    'data': [
        'report/report_invoice.xml',
    ],
    'installable': True,
    'application': False,
}