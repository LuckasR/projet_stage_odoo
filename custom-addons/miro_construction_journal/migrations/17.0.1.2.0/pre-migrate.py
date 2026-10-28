"""Avant que l'avancement des phases devienne calculé depuis les journaux :
garde de côté les avancements saisis à la main (ou venus de l'ancien
« Déclarer la consommation »), que post-migrate reprend dans un journal."""


def migrate(cr, version):
    if not version:
        return
    cr.execute("DROP TABLE IF EXISTS miro_journal_progress_backup")
    cr.execute("""CREATE TABLE miro_journal_progress_backup AS
                  SELECT id AS task_id, project_id, x_avancement_manuel AS progress
                  FROM project_task
                  WHERE x_avancement_manuel > 0 AND project_id IS NOT NULL""")
