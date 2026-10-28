"""Les lignes des journaux déjà validés prennent le valideur et la date de
validation de leur journal."""

LINE_TABLES = ('miro_site_journal_work', 'miro_site_journal_labor', 'miro_site_journal_material',
               'miro_site_journal_equipment', 'miro_site_journal_expense')


def migrate(cr, version):
    if not version:
        return
    for table in LINE_TABLES:
        cr.execute(f"""UPDATE {table} l
                       SET validated_by_id = j.validated_by_id, validated_on = j.validated_on
                       FROM miro_site_journal j
                       WHERE l.journal_id = j.id AND l.state = 'validated'""")
