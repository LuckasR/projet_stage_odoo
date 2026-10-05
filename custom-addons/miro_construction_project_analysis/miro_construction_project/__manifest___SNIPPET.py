# À FUSIONNER dans ton __manifest__.py
{
    'depends': ['project', 'mail'],   # + tes dépendances actuelles
    'data': [
        'security/ir.model.access.csv',   # ajoute ces lignes à ton fichier existant
        'data/construction_phase_template_data.xml',
        'data/ir_cron.xml',
        # + tes vues (à créer, voir remarque)
    ],
}
