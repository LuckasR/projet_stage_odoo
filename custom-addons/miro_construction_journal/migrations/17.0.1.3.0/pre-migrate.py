"""Les lignes du journal ont désormais leur propre état (brouillon /
validé) au lieu de recopier celui du journal, et une phase peut avoir
plusieurs travaux le même jour.

La colonne `state` des lignes contenait l'état du journal : une ligne d'un
journal validé est validée, toutes les autres repartent en brouillon."""

LINE_TABLES = ('miro_site_journal_work', 'miro_site_journal_labor', 'miro_site_journal_material',
               'miro_site_journal_equipment', 'miro_site_journal_expense')


def migrate(cr, version):
    if not version:
        return
    for table in LINE_TABLES:
        cr.execute(f"""UPDATE {table}
                       SET state = CASE WHEN state = 'validated' THEN 'validated' ELSE 'draft' END""")
    cr.execute("""ALTER TABLE miro_site_journal_work
                  DROP CONSTRAINT IF EXISTS miro_site_journal_work_journal_task_uniq""")
