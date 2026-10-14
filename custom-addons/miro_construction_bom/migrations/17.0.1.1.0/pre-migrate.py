"""Passage de la nomenclature maison (construction.bom, supprimée de
construction_product_management) aux nomenclatures natives (mrp.bom).

Avant le chargement du module, on détache tout ce qui pointe encore vers
l'ancienne table : sans cela, sa suppression est refusée par PostgreSQL
(construction_phase_template_line_bom_id_fkey) et la nouvelle clé vers
mrp_bom ne peut pas être posée.

Rien n'est perdu : `_install_default_boms` (data/default_boms.xml, rejoué à
la mise à jour) recrée les recettes livrées en natif, les rattache aux
phases restées sans nomenclature et recalcule les besoins des phases qui
n'en ont plus. Un besoin déjà commandé ou consommé est conservé, seul son
lien vers l'ancienne recette est retiré."""
import logging

_logger = logging.getLogger(__name__)


def _table_exists(cr, table):
    cr.execute("SELECT to_regclass(%s)", (table,))
    return bool(cr.fetchone()[0])


def migrate(cr, version):
    if not version or not _table_exists(cr, 'construction_bom'):
        return

    cr.execute("UPDATE construction_phase_template_line SET bom_id = NULL WHERE bom_id IS NOT NULL")
    _logger.info("%d phase(s) de gabarit détachée(s) de l'ancienne nomenclature", cr.rowcount)

    if _table_exists(cr, 'construction_element_type_bom'):
        # bom_id y est obligatoire : la surcharge est à ressaisir en natif
        cr.execute("DELETE FROM construction_element_type_bom")
        _logger.info("%d nomenclature(s) propre(s) à un type supprimée(s)", cr.rowcount)

    if _table_exists(cr, 'construction_material_need'):
        cr.execute("""
            DELETE FROM construction_material_need n
             WHERE n.purchase_line_id IS NULL
               AND NOT EXISTS (SELECT 1 FROM stock_move m
                                WHERE m.construction_need_id = n.id AND m.state = 'done')
        """)
        _logger.info("%d besoin(s) non commandé(s) supprimé(s), recalculés à la mise à jour",
                     cr.rowcount)
        cr.execute("UPDATE construction_material_need SET bom_id = NULL, bom_line_id = NULL")
