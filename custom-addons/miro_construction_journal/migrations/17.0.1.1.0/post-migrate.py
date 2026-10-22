"""Journaux de la première version : les lignes portaient leur phase
directement et l'avancement était une ligne à part (miro_site_journal_progress).
Elles sont regroupées en travaux, un par (journal, phase), qui reprennent la
quantité réalisée. Rien n'est rejoué : stock et avancement ont déjà été mis à
jour à la validation."""
from odoo import SUPERUSER_ID, api

LINE_TABLES = {
    'miro.site.journal.labor': 'miro_site_journal_labor',
    'miro.site.journal.material': 'miro_site_journal_material',
    'miro.site.journal.equipment': 'miro_site_journal_equipment',
    'miro.site.journal.expense': 'miro_site_journal_expense',
}


def _table_exists(cr, table):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", [table])
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'miro_journal_unlocked': True})

    orphans = {}
    for model, table in LINE_TABLES.items():
        cr.execute(f"SELECT id, journal_id, task_id FROM {table} "
                   "WHERE work_id IS NULL AND task_id IS NOT NULL")
        for line_id, journal_id, task_id in cr.fetchall():
            orphans.setdefault((journal_id, task_id), []).append((model, line_id))

    progress = {}
    if _table_exists(cr, 'miro_site_journal_progress'):
        cr.execute("SELECT journal_id, task_id, SUM(qty_done), MAX(progress_pct) "
                   "FROM miro_site_journal_progress GROUP BY journal_id, task_id")
        for journal_id, task_id, qty_done, pct in cr.fetchall():
            progress[(journal_id, task_id)] = (qty_done or 0.0, pct or 0.0)

    Work = env['miro.site.journal.work']
    for key in sorted(set(orphans) | set(progress)):
        journal_id, task_id = key
        qty_done, pct = progress.get(key, (0.0, 0.0))
        work = Work.search([('journal_id', '=', journal_id), ('task_id', '=', task_id)], limit=1) \
            or Work.create({'journal_id': journal_id, 'task_id': task_id,
                            'qty_done': qty_done, 'progress_pct': pct})
        for model, line_id in orphans.get(key, []):
            env[model].browse(line_id).write({'work_id': work.id})

    if _table_exists(cr, 'miro_site_journal_progress'):
        cr.execute("DROP TABLE miro_site_journal_progress")
