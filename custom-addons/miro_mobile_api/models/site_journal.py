from odoo import api, fields, models


def _bump(records, table):
    if not records.ids:
        return
    # SQL : un simple compteur, sans repasser par write() ni les verrous
    records.env.cr.execute(
        f"UPDATE {table} SET mobile_version = mobile_version + 1 WHERE id IN %s",
        [tuple(records.ids)])
    records.invalidate_recordset(['mobile_version'])


class MiroSiteJournal(models.Model):
    """Version de l'en-tête du journal pour l'application mobile (météo,
    heures d'arrêt, observations, frais du chantier, état). Chaque travail a
    la sienne : deux personnes peuvent saisir des travaux différents du même
    journal sans conflit. Le téléphone renvoie la version sur laquelle il a
    travaillé ; si elle a changé entre-temps, c'est un conflit."""
    _inherit = 'miro.site.journal'

    mobile_version = fields.Integer("Version", default=1, readonly=True, copy=False)

    def _mobile_bump(self):
        _bump(self, 'miro_site_journal')

    def write(self, vals):
        res = super().write(vals)
        if set(vals) - self._LOCK_FREE:
            self._mobile_bump()
        return res


class MiroSiteJournalWork(models.Model):
    _inherit = 'miro.site.journal.work'

    # Identifiant donné par le téléphone : il retrouve sa ligne après envoi
    mobile_uuid = fields.Char(index=True, readonly=True, copy=False)
    mobile_version = fields.Integer("Version", default=1, readonly=True, copy=False)

    def _mobile_bump(self):
        _bump(self, 'miro_site_journal_work')

    def write(self, vals):
        res = super().write(vals)
        if set(vals) - {'sequence', 'mobile_uuid'}:
            self._mobile_bump()
        return res


class MiroSiteJournalLine(models.AbstractModel):
    """Une ligne qui change fait changer la version de son travail, ou de
    l'en-tête du journal pour les frais du chantier."""
    _inherit = 'miro.site.journal.line'

    mobile_uuid = fields.Char(index=True, readonly=True, copy=False)

    def _mobile_touch(self):
        self.work_id._mobile_bump()
        self.filtered(lambda l: not l.work_id).journal_id._mobile_bump()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._mobile_touch()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if set(vals) - {'mobile_uuid'}:
            self._mobile_touch()
        return res

    def unlink(self):
        works, journals = self.work_id, self.filtered(lambda l: not l.work_id).journal_id
        res = super().unlink()
        works.exists()._mobile_bump()
        journals.exists()._mobile_bump()
        return res
