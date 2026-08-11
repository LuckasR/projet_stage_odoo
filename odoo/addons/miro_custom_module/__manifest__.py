{
    'name': 'miro custom module',
    'version': '17.0.1.0.0',
    'summary': 'miro custom module',
    'description': '''
Module miro custom module
''',
    'author': 'L. M. Rabemiafara, Miro K.E.',
    'website': 'https://www.example.com',
    'license': 'LGPL-3',
    'category': 'Tools',
    'depends': ['base'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/menu.xml',
        'views/views.xml', 
        'data/data.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
