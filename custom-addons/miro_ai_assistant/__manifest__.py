{
    'name': "Miro Assistant (IA)",
    'summary': "Assistant IA dans Discuss : avancement, retards, matériaux et planning des chantiers",
    'description': """
Miro Assistant
==============
Un bot de messagerie (Discuss) et une bulle flottante en bas à droite de
l'écran. On lui pose une question en français (« Où en est le chantier
Villa Ivato ? ») ; il interroge la base au travers d'outils en lecture seule,
avec les droits de l'utilisateur qui pose la question, et répond.

Le fournisseur d'IA n'est pas figé : tout service compatible avec l'API
Chat Completions d'OpenAI (Groq, OpenAI, Mistral, OpenRouter, Ollama...).
URL, clé et modèle se règlent dans Paramètres → Miro Assistant.
""",
    'version': '17.0.1.0.0',
    'category': 'Productivity/Discuss',
    'author': "MIRO K.E.",
    'license': 'LGPL-3',
    'depends': ['mail', 'queue_job', 'miro_construction_project'],
    'data': [
        'data/assistant_data.xml',
        'data/queue_job_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'miro_ai_assistant/static/src/bubble/*',
        ],
    },
    'installable': True,
    'application': False,
}
