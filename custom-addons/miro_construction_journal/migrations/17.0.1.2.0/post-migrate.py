"""L'avancement d'une phase vient désormais des seuls journaux validés.

1. Une phase sans métré se déclare en état (pas commencé / en cours / fini) :
   les travaux existants reprennent l'état correspondant à leur ancien %.
2. Les avancements saisis à la main que les journaux ne couvrent pas sont
   repris dans un « Journal de reprise » validé par chantier : rien n'est
   perdu, et ils se corrigent comme tout journal.
3. L'avancement des tâches mères et des chantiers est recalculé, pondéré
   par le coût prévu."""
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields


def migrate(cr, version):
    if not version:
        return
    cr.execute("""SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'miro_site_journal_work' AND column_name = 'progress_pct'""")
    if cr.fetchone():
        cr.execute("""UPDATE miro_site_journal_work
                      SET status = CASE WHEN progress_pct >= 100 THEN 'done'
                                        WHEN progress_pct > 0 THEN 'doing'
                                        ELSE 'todo' END
                      WHERE progress_pct IS NOT NULL""")
        cr.execute("ALTER TABLE miro_site_journal_work DROP COLUMN progress_pct")

    env = api.Environment(cr, SUPERUSER_ID, {'miro_journal_unlocked': True})
    Task = env['project.task']

    cr.execute("SELECT to_regclass('miro_journal_progress_backup')")
    if cr.fetchone()[0]:
        cr.execute("SELECT task_id, project_id, progress FROM miro_journal_progress_backup")
        backup = cr.fetchall()
        by_project = {}
        for task_id, project_id, progress in backup:
            task = Task.browse(task_id).exists()
            if task and not task.child_ids and (task.x_avancement_manuel or 0.0) < progress - 0.05:
                by_project.setdefault(project_id, []).append((task, progress))
        Journal = env['miro.site.journal']
        today = fields.Date.context_today(Journal)
        for project_id, items in by_project.items():
            day = today
            while Journal.search_count([('project_id', '=', project_id), ('date', '=', day)]):
                day -= timedelta(days=1)
            works = []
            for task, progress in items:
                vals = {'task_id': task.id, 'note': "Reprise de l'avancement saisi à la main (%d %%)" % round(progress)}
                if task.phase_qty:
                    vals['qty_done'] = task.phase_qty * progress / 100.0 - task.x_qty_realisee
                else:
                    vals['status'] = 'done' if progress >= 100 else 'doing'
                works.append((0, 0, vals))
            journal = Journal.create({
                'project_id': project_id, 'date': day, 'work_ids': works,
                'notes': "<p>Journal créé à la mise à jour du module : il reprend les avancements "
                         "saisis à la main avant que l'avancement ne vienne que des journaux.</p>",
            })
            journal.action_validate()
        cr.execute("DROP TABLE miro_journal_progress_backup")

    # Moyennes désormais pondérées par le coût prévu
    tasks = Task.with_context(active_test=False).search([])
    env.add_to_compute(Task._fields['x_avancement_global'], tasks)
    projects = env['project.project'].with_context(active_test=False).search([])
    env.add_to_compute(projects._fields['x_avancement_global'], projects)
    env.flush_all()
