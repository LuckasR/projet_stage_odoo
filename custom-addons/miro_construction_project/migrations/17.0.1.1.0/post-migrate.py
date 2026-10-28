"""Les noms de calque cherchés par l'analyse DXF passent dans des conventions
de calques (construction.dxf.layer.convention).

1. Le « mot-clé du calque » des types d'éléments (moteur « blocs ») devient
   un nom de calque de la convention Miro. Un mot-clé était cherché
   « contenu dans » le nom du calque : il devient le motif *MOT*.
2. Les chantiers existants prennent la convention « All ».
3. L'ancienne colonne est supprimée."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    miro = env.ref('miro_construction_project.dxf_layer_convention_miro', raise_if_not_found=False)
    all_conv = env.ref('miro_construction_project.dxf_layer_convention_all', raise_if_not_found=False)

    cr.execute("""SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'construction_element_type'
                    AND column_name = 'dxf_layer_keyword'""")
    if cr.fetchone():
        cr.execute("""SELECT id, dxf_layer_keyword FROM construction_element_type
                      WHERE COALESCE(TRIM(dxf_layer_keyword), '') != ''""")
        rows = cr.fetchall()
        if rows and miro:
            env['construction.dxf.layer.name'].create([{
                'convention_id': miro.id,
                'role': 'element_type',
                'element_type_id': type_id,
                'name': '*%s*' % keyword.strip(),
            } for type_id, keyword in rows])
        cr.execute("ALTER TABLE construction_element_type DROP COLUMN dxf_layer_keyword")

    if all_conv:
        cr.execute("""UPDATE project_project SET dxf_layer_convention_id = %s
                      WHERE dxf_layer_convention_id IS NULL""", [all_conv.id])
