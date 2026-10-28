import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext, plaintext2html

_logger = logging.getLogger(__name__)

# Journaux et incidents résolus envoyés au téléphone : les N derniers jours
HISTORY_DAYS = 30

PHOTO_MODELS = {'journal': 'miro.site.journal', 'incident': 'construction.task.incident'}


def _date(value):
    return fields.Date.to_string(value) if value else None


class MiroMobileApi(models.AbstractModel):
    """Ce que l'application mobile lit et écrit, dans le format qu'elle
    attend. Tout tourne sous l'utilisateur du téléphone : les droits Odoo
    s'appliquent comme au bureau, restreints à ses chantiers.

    Le téléphone travaille hors-ligne : il télécharge un instantané
    (_snapshot), puis renvoie ses saisies sous forme d'opérations (_push).
    Une opération porte la version de l'enregistrement sur laquelle elle a
    été saisie ; si l'enregistrement a bougé depuis, elle est refusée comme
    conflit, avec la version du serveur, et c'est l'utilisateur qui tranche."""
    _name = 'miro.mobile.api'
    _description = "API de l'application mobile"

    # ------------------------------------------------------------------
    # Périmètre : les chantiers en cours de l'utilisateur
    # ------------------------------------------------------------------
    @api.model
    def _projects(self):
        uid = self.env.uid
        return self.env['project.project'].search([
            '|', ('x_responsable_chantier_id', '=', uid), ('user_id', '=', uid),
            ('x_status', 'not in', ('termine', 'annule'))])

    @api.model
    def _project(self, project_id):
        project = self._projects().filtered(lambda p: p.id == project_id)
        if not project:
            raise AccessError(_("Ce chantier ne vous est pas attribué."))
        return project

    @api.model
    def _task(self, task_id, projects, phase=True):
        task = self.env['project.task'].browse(int(task_id or 0)).exists()
        if not task or task.project_id not in projects or (phase and task.child_ids):
            raise UserError(_("Phase inconnue sur ce chantier (%s).") % task_id)
        return task

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    @api.model
    def _snapshot(self):
        projects = self._projects()
        since = fields.Date.context_today(self) - timedelta(days=HISTORY_DAYS)
        phases = self.env['project.task'].search(
            [('project_id', 'in', projects.ids), ('child_ids', '=', False)],
            order='project_id, sequence, id')
        journals = self.env['miro.site.journal'].search([
            ('project_id', 'in', projects.ids),
            '|', ('date', '>=', since), ('state', '!=', 'validated')])
        incidents = self.env['construction.task.incident'].search([
            ('project_id', 'in', projects.ids),
            '|', ('etat', '!=', 'resolu'), ('date_incident', '>=', since)])
        # sudo : la fiche employé est réservée aux RH ; on n'en lit que le nom
        employees = self.env['hr.employee'].sudo().search(
            [('company_id', 'in', self.env.companies.ids)])
        Journal, Work, Incident = (self.env[m] for m in (
            'miro.site.journal', 'miro.site.journal.work', 'construction.task.incident'))

        def selection(model, field):
            return model._fields[field]._description_selection(self.env)

        return {
            'server_time': fields.Datetime.to_string(fields.Datetime.now()),
            'user': {'id': self.env.user.id, 'name': self.env.user.name},
            'hours_per_day': self.env.company.miro_hours_per_day or 8.0,
            'currency': self.env.company.currency_id.name,
            'selections': {
                'weather': selection(Journal, 'weather'),
                'journal_state': selection(Journal, 'state'),
                'work_status': selection(Work, 'status'),
                'line_state': selection(Work, 'state'),
                'incident_gravite': selection(Incident, 'gravite'),
                'incident_etat': selection(Incident, 'etat'),
            },
            'projects': [self._project_data(p) for p in projects],
            'phases': [self._phase_data(t) for t in phases],
            'employees': [{'id': e.id, 'name': e.name, 'trade': e.miro_trade_id.name or None}
                          for e in employees],
            'equipment': [{'id': e.id, 'name': e.name}
                          for e in self.env['miro.site.equipment'].search([])],
            'journals': [self._journal_data(j) for j in journals],
            'incidents': [self._incident_data(i) for i in incidents],
        }

    @api.model
    def _project_data(self, project):
        return {
            'id': project.id,
            'name': project.name,
            'status': project.x_status,
            'address': ', '.join(filter(None, [project.x_adresse_chantier,
                                               project.x_ville_chantier])) or None,
            'date_start': _date(project.x_date_debut_travaux),
            'date_end': _date(project.x_date_fin_prevue),
            'progress': project.x_avancement_global,
            'site_manager': project.x_responsable_chantier_id.name or None,
        }

    @api.model
    def _phase_data(self, task):
        path, parent = [], task.parent_id
        while parent:
            path.insert(0, parent.name)
            parent = parent.parent_id
        return {
            'id': task.id,
            'project_id': task.project_id.id,
            'name': task.name,
            'path': ' / '.join(path) or None,
            'deadline': _date(task.date_deadline),
            'qty': task.phase_qty,
            'unit': task.phase_qty_label or None,
            'qty_done': task.x_qty_realisee,
            'progress': task.x_avancement_manuel,
            'crew': task.miro_crew_id.name or None,
            'needs': [{
                'id': need.id,
                'product': need.product_id.display_name,
                'uom': need.product_id.uom_id.name,
                'qty': need.product_qty,
                'remaining': need.qty_remaining,
            } for need in task.material_need_ids.filtered('product_id')],
        }

    @api.model
    def _photos(self, record):
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', record._name), ('res_id', '=', record.id),
            ('mimetype', '=like', 'image/%')])
        return [{'id': a.id, 'name': a.name} for a in attachments]

    @api.model
    def _uid(self, record):
        """Identifiant d'une ligne pour le téléphone : celui qu'il lui a
        donné, ou srv-<id> pour une ligne saisie au bureau."""
        return record.mobile_uuid or f'srv-{record.id}'

    @api.model
    def _find(self, records, uid):
        if not uid:
            return records.browse()
        if uid.startswith('srv-'):
            return records.filtered(lambda r: r.id == int(uid[4:]))
        return records.filtered(lambda r: r.mobile_uuid == uid)

    @api.model
    def _journal_data(self, journal):
        def line(l, **values):
            return {'uid': self._uid(l), 'state': l.state, **values}

        def equipment(lines):
            return [line(l, equipment_id=l.equipment_id.id, hours=l.hours) for l in lines]

        def expenses(lines):
            return [line(l, name=l.name, amount=l.amount) for l in lines]

        return {
            'id': journal.id,
            'project_id': journal.project_id.id,
            'date': _date(journal.date),
            'state': journal.state,
            'version': journal.mobile_version,
            'author': journal.user_id.name or None,
            'weather': journal.weather or None,
            'hours_lost': journal.hours_lost,
            'notes': html2plaintext(journal.notes) if journal.notes else None,
            'works': [{
                'uid': self._uid(work),
                'version': work.mobile_version,
                'state': work.state,
                'validated_by': work.validated_by_id.name or None,
                'task_id': work.task_id.id,
                'qty_done': work.qty_done,
                'correction_reason': work.correction_reason or None,
                'status': work.status or None,
                'note': work.note or None,
                'labor': [line(l, employee_id=l.employee_id.id, hours=l.hours) for l in work.labor_line_ids],
                'materials': [line(l, need_id=l.need_id.id, quantity=l.quantity)
                              for l in work.material_line_ids],
                'equipment': equipment(work.equipment_line_ids),
                'expenses': expenses(work.expense_line_ids),
            } for work in journal.work_ids],
            'site_equipment': equipment(journal.site_equipment_line_ids),
            'site_expenses': expenses(journal.site_expense_line_ids),
            'photos': self._photos(journal),
        }

    @api.model
    def _incident_data(self, incident):
        return {
            'id': incident.id,
            'project_id': incident.project_id.id,
            'task_id': incident.task_id.id,
            'name': incident.name,
            'description': incident.description or None,
            'date': _date(incident.date_incident),
            'gravite': incident.gravite,
            'etat': incident.etat,
            'assignee': incident.responsable_id.name or None,
            'version': fields.Datetime.to_string(incident.write_date),
            'photos': self._photos(incident),
        }

    # ------------------------------------------------------------------
    # Écriture : les opérations saisies hors-ligne
    # ------------------------------------------------------------------
    @api.model
    def _push(self, ops, device):
        """Applique les opérations dans l'ordre, chacune à part : une
        opération en erreur ou en conflit n'empêche pas les suivantes.
        Le journal est découpé en un en-tête et ses travaux, chacun avec sa
        version : deux personnes peuvent saisir des travaux différents du
        même journal sans conflit."""
        handlers = {
            'journal.header': self._op_journal_header,
            'work.upsert': self._op_work_upsert,
            'work.delete': self._op_work_delete,
            'incident.create': self._op_incident_create,
            'incident.update': self._op_incident_update,
        }
        Op = self.env['miro.mobile.op'].sudo()
        results = []
        for op in ops:
            uuid, kind = op.get('uuid'), op.get('kind')
            if not uuid or kind not in handlers:
                results.append({'uuid': uuid, 'status': 'error',
                                'message': _("Opération invalide.")})
                continue
            done = Op.search([('uuid', '=', uuid)], limit=1)
            if done:
                results.append(json.loads(done.result))
                continue
            try:
                with self.env.cr.savepoint():
                    result = {'uuid': uuid, **handlers[kind](op)}
                    if result['status'] == 'ok':
                        Op.create({'uuid': uuid, 'device_id': device.id, 'kind': kind,
                                   'result': json.dumps(result)})
            except (UserError, AccessError, ValueError) as e:
                result = {'uuid': uuid, 'status': 'error', 'message': str(e.args[0] if e.args else e)}
            except Exception:
                _logger.exception("Opération mobile %s (%s) en échec", uuid, kind)
                result = {'uuid': uuid, 'status': 'error',
                          'message': _("Erreur interne du serveur.")}
            results.append(result)
        return results

    @api.model
    def _conflict(self, reason, message, record=None):
        return {'status': 'conflict', 'reason': reason, 'message': message, 'record': record}

    @api.model
    def _journal(self, data, create=True):
        """Le journal du chantier et du jour de l'opération, créé au besoin."""
        project = self._project(int(data.get('project_id') or 0))
        date = fields.Date.to_date(data.get('date'))
        if not date:
            raise UserError(_("Date du journal manquante."))
        Journal = self.env['miro.site.journal']
        journal = Journal.search([('project_id', '=', project.id), ('date', '=', date)], limit=1)
        if not journal and create:
            journal = Journal.create({'project_id': project.id, 'date': date})
        return journal

    @api.model
    def _locked(self, journal):
        return self._conflict('locked', _(
            "Ce journal a été validé par le conducteur de travaux : il ne peut plus être modifié."),
            self._journal_data(journal))

    @api.model
    def _sync_lines(self, lines, payload, vals_of, owner):
        """Aligne les lignes d'Odoo sur celles du téléphone, reconnues par
        leur uid. Une ligne validée n'est plus touchée ; une ligne en
        brouillon absente du téléphone est supprimée. Renvoie les lignes
        que le téléphone demande de valider."""
        keep, to_validate = lines.browse(), lines.browse()
        for item in payload or []:
            line = self._find(lines, item.get('uid'))
            if line.state == 'validated':
                keep |= line
                continue
            vals = vals_of(item)
            if vals is None:  # ligne vide (matière à 0) : comme absente
                continue
            if line:
                line.write(vals)
            else:
                if not item.get('uid'):
                    raise UserError(_("Ligne sans identifiant."))
                line = lines.create({**vals, **owner, 'mobile_uuid': item['uid']})
            keep |= line
            if item.get('validate'):
                to_validate |= line
        (lines - keep).filtered(lambda l: l.state == 'draft').unlink()
        return to_validate

    @staticmethod
    def _equipment_vals(item):
        return {'equipment_id': int(item['equipment_id']), 'hours': float(item.get('hours') or 0)}

    @staticmethod
    def _expense_vals(item):
        return {'name': item.get('name'), 'amount': float(item.get('amount') or 0)}

    @api.model
    def _op_journal_header(self, op):
        """En-tête du journal : météo, heures d'arrêt, observations, frais
        du chantier. `submit` prévient le conducteur que la journée est
        finie ; le journal reste ouvert à de nouvelles lignes."""
        data = op.get('data') or {}
        journal = self._journal(data, create=False)
        base = op.get('base_version')
        if journal.state == 'validated':
            return self._locked(journal)
        # Version 1 : journal créé par un travail, en-tête jamais saisi
        if journal and base is None and journal.mobile_version > 1:
            return self._conflict('exists', _(
                "Ce journal a déjà été rempli par quelqu'un d'autre."), self._journal_data(journal))
        if journal and base is not None and journal.mobile_version != base:
            return self._conflict('modified', _(
                "Ce journal a été modifié depuis votre dernière synchronisation."),
                self._journal_data(journal))
        if not journal and base is not None:
            return self._conflict('deleted', _("Ce journal a été supprimé au bureau."))
        journal = journal or self._journal(data)

        journal.write({
            'weather': data.get('weather') or False,
            'hours_lost': float(data.get('hours_lost') or 0),
            'notes': plaintext2html(data['notes']) if data.get('notes') else False,
        })
        owner = {'journal_id': journal.id}
        to_validate = [
            self._sync_lines(journal.site_equipment_line_ids, data.get('site_equipment'),
                             self._equipment_vals, owner),
            self._sync_lines(journal.site_expense_line_ids, data.get('site_expenses'),
                             self._expense_vals, owner),
        ]
        for lines in to_validate:
            lines.action_validate_line()
        if op.get('submit') and journal.state == 'draft':
            journal.action_submit()
        return {'status': 'ok', 'record': self._journal_data(journal)}

    @api.model
    def _op_work_upsert(self, op):
        """Un travail du jour et ses lignes. `validate` sur le travail le
        valide en entier ; sur une ligne, la valide seule."""
        data = op.get('data') or {}
        journal = self._journal(data)
        if journal.state == 'validated':
            return self._locked(journal)
        work = self._find(journal.work_ids, data.get('uid'))
        base = op.get('base_version')
        if work.state == 'validated':
            return self._conflict('locked', _(
                "Ce travail a été validé entre-temps : il ne peut plus être modifié."),
                self._journal_data(journal))
        # Sans version de base, un uid déjà connu ne peut venir que de ce
        # téléphone (envoi dont la réponse s'est perdue) : pas de conflit.
        if work and base is not None and work.mobile_version != base:
            return self._conflict('modified', _(
                "Ce travail a été modifié depuis votre dernière synchronisation."),
                self._journal_data(journal))
        if not work and base is not None:
            return self._conflict('deleted', _("Ce travail a été supprimé au bureau."),
                                  self._journal_data(journal))

        task = self._task(data.get('task_id'), journal.project_id)
        vals = {
            'task_id': task.id,
            'qty_done': float(data.get('qty_done') or 0),
            'correction_reason': data.get('correction_reason') or False,
            'status': data.get('status') or 'doing',
            'note': data.get('note') or False,
        }
        if work:
            work.write(vals)
        else:
            if not data.get('uid'):
                raise UserError(_("Travail sans identifiant."))
            work = self.env['miro.site.journal.work'].create(
                {**vals, 'journal_id': journal.id, 'mobile_uuid': data['uid']})

        def material_vals(item):
            need = task.material_need_ids.filtered(lambda n: n.id == int(item['need_id']))
            if not need:
                raise UserError(_("%s : matériau inconnu pour cette phase.") % task.name)
            quantity = float(item.get('quantity') or 0)
            return {'need_id': need.id, 'quantity': quantity} if quantity else None

        owner = {'work_id': work.id}
        to_validate = [
            self._sync_lines(work.labor_line_ids, data.get('labor'), lambda item: {
                'employee_id': int(item['employee_id']), 'hours': float(item.get('hours') or 0),
            }, owner),
            self._sync_lines(work.material_line_ids, data.get('materials'), material_vals, owner),
            self._sync_lines(work.equipment_line_ids, data.get('equipment'), self._equipment_vals, owner),
            self._sync_lines(work.expense_line_ids, data.get('expenses'), self._expense_vals, owner),
        ]
        for lines in to_validate:
            lines.action_validate_line()
        if op.get('validate'):
            work.action_validate_line()
        return {'status': 'ok', 'record': self._journal_data(journal)}

    @api.model
    def _op_work_delete(self, op):
        data = op.get('data') or {}
        journal = self._journal(data, create=False)
        work = self._find(journal.work_ids, data.get('uid'))
        if not work:
            return {'status': 'ok', 'record': self._journal_data(journal) if journal else None}
        if journal.state == 'validated':
            return self._locked(journal)
        if work.state == 'validated' or any(
                lines.filtered(lambda l: l.state == 'validated') for lines in work._sub_lines()):
            return self._conflict('locked', _(
                "Ce travail a des lignes validées : il ne peut plus être supprimé."),
                self._journal_data(journal))
        if op.get('base_version') is not None and work.mobile_version != op['base_version']:
            return self._conflict('modified', _(
                "Ce travail a été modifié depuis votre dernière synchronisation."),
                self._journal_data(journal))
        work.unlink()
        return {'status': 'ok', 'record': self._journal_data(journal)}

    @api.model
    def _op_incident_create(self, op):
        data = op.get('data') or {}
        task = self._task(data.get('task_id'), self._projects(), phase=False)
        if not (data.get('name') or '').strip():
            raise UserError(_("Donnez un titre à l'incident."))
        incident = self.env['construction.task.incident'].create({
            'task_id': task.id,
            'name': data['name'].strip(),
            'description': data.get('description') or False,
            'date_incident': data.get('date') or fields.Date.context_today(self),
            'gravite': data.get('gravite') or 'moyenne',
        })
        return {'status': 'ok', 'record': self._incident_data(incident)}

    @api.model
    def _op_incident_update(self, op):
        data = op.get('data') or {}
        incident = self.env['construction.task.incident'].browse(int(op.get('id') or 0)).exists()
        if not incident or incident.project_id not in self._projects():
            return self._conflict('deleted', _("Cet incident n'existe plus."))
        if fields.Datetime.to_string(incident.write_date) != op.get('base_version'):
            return self._conflict('modified', _(
                "Cet incident a été modifié depuis votre dernière synchronisation."),
                self._incident_data(incident))
        incident.write({k: data[k] for k in ('name', 'description', 'gravite', 'etat') if k in data})
        return {'status': 'ok', 'record': self._incident_data(incident)}

    # ------------------------------------------------------------------
    # Photos
    # ------------------------------------------------------------------
    @api.model
    def _photo_target(self, model, res_id):
        record = self.env[PHOTO_MODELS[model]].browse(int(res_id or 0)).exists() \
            if model in PHOTO_MODELS else None
        if not record or record.project_id not in self._projects():
            raise AccessError(_("Enregistrement introuvable sur vos chantiers."))
        return record

    @api.model
    def _upload_photo(self, device, uuid, model, res_id, upload):
        Op = self.env['miro.mobile.op'].sudo()
        done = Op.search([('uuid', '=', uuid)], limit=1) if uuid else Op
        if done:
            return json.loads(done.result)
        if not uuid or not upload:
            raise UserError(_("Photo ou identifiant manquant."))
        record = self._photo_target(model, res_id)
        attachment = self.env['ir.attachment'].create({
            'name': upload.filename or 'photo.jpg',
            'raw': upload.read(),
            'res_model': record._name,
            'res_id': record.id,
        })
        result = {'uuid': uuid, 'status': 'ok', 'id': attachment.id}
        Op.create({'uuid': uuid, 'device_id': device.id, 'kind': 'photo.upload',
                   'result': json.dumps(result)})
        return result

    @api.model
    def _photo(self, attachment_id):
        attachment = self.env['ir.attachment'].browse(attachment_id).exists()
        model = next((k for k, v in PHOTO_MODELS.items() if v == attachment.res_model), None)
        if not attachment or not model:
            raise AccessError(_("Photo introuvable."))
        self._photo_target(model, attachment.res_id)
        return attachment
