"""Outils que l'assistant peut appeler.

Chaque outil est une lecture de la base, sans `sudo()` : il s'exécute avec
les droits de l'utilisateur qui pose la question. Un chef de chantier ne
reçoit donc que ce qu'il verrait dans Odoo. Aucun outil n'écrit.

Les résultats sont des dictionnaires simples, sérialisés en JSON pour le
modèle : il y lit les chiffres, il ne les invente pas.
"""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.osv import expression


def _project_schema(description):
    return {'type': 'object', 'additionalProperties': False, 'required': ['project_id'],
            'properties': {'project_id': {'type': 'integer', 'description': description}}}


TOOLS = [
    {
        'name': 'find_projects',
        'description': (
            "Recherche les chantiers (projets) par nom, client, ville ou maître d'ouvrage. "
            "À appeler en premier dès qu'un chantier est cité par son nom, pour obtenir son "
            "identifiant. Une chaîne vide liste les chantiers en cours."),
        'input_schema': {
            'type': 'object', 'additionalProperties': False, 'required': ['query'],
            'properties': {'query': {'type': 'string',
                                     'description': "Nom ou partie du nom du chantier ; vide pour tout lister."}},
        },
    },
    {
        'name': 'get_project_progress',
        'description': (
            "Avancement d'un chantier : pourcentage global, statut, dates, nombre de tâches "
            "terminées / en cours / non commencées / en retard, avancement de chaque ouvrage "
            "(tâche racine) et coûts (budget, prévu, réel)."),
        'input_schema': _project_schema("Identifiant du chantier (donné par find_projects)."),
    },
    {
        'name': 'get_progress_by_level',
        'description': (
            "Avancement des phases de construction d'un chantier par niveau (fondations, RDC, "
            "R+1...) et par type d'élément (poteau, poutre, dalle, mur...). Sert à dire où en "
            "est la structure."),
        'input_schema': _project_schema("Identifiant du chantier."),
    },
    {
        'name': 'get_late_tasks',
        'description': "Tâches d'un chantier dont l'échéance est dépassée sans être terminées.",
        'input_schema': _project_schema("Identifiant du chantier."),
    },
    {
        'name': 'search_tasks',
        'description': (
            "Recherche des tâches ou phases d'un chantier par nom ou par élément de construction "
            "(ex. « coulage P3 », « dalle R+1 », « fondation »). Renvoie leur avancement, état, "
            "dates prévues et équipe."),
        'input_schema': {
            'type': 'object', 'additionalProperties': False, 'required': ['project_id', 'query'],
            'properties': {
                'project_id': {'type': 'integer', 'description': "Identifiant du chantier."},
                'query': {'type': 'string', 'description': "Texte à chercher dans le nom de la tâche ou de l'élément."},
            },
        },
    },
    {
        'name': 'get_material_status',
        'description': (
            "Besoins en matériaux d'un chantier : coût prévu et consommé, avancement de "
            "l'approvisionnement (commandé, reçu, consommé), matériaux en rupture ou en "
            "dépassement, principaux matériaux."),
        'input_schema': _project_schema("Identifiant du chantier."),
    },
    {
        'name': 'get_planning_summary',
        'description': (
            "Planning proposé d'un chantier : dates de début et de fin planifiées, durée en "
            "jours ouvrés, coût de main-d'œuvre, phases en cours cette semaine et à venir."),
        'input_schema': _project_schema("Identifiant du chantier."),
    },
]


# États natifs des tâches, en français quelle que soit la langue de l'interface
TASK_STATES = {
    '01_in_progress': "En cours", '02_changes_requested': "Modifications demandées",
    '03_approved': "Approuvée", '04_waiting_normal': "En attente",
    '1_done': "Terminée", '1_canceled': "Annulée",
}


class ToolError(Exception):
    """Erreur renvoyée au modèle (projet introuvable...), pas à l'utilisateur."""


class MiroAssistantTools(models.AbstractModel):
    _name = 'miro.ai.assistant.tools'
    _description = "Outils de Miro Assistant"

    # ------------------------------------------------------------------
    # Aides
    # ------------------------------------------------------------------
    @api.model
    def _project(self, project_id):
        # search() et non browse() : les règles d'accès s'appliquent
        project = self.env['project.project'].search([('id', '=', int(project_id or 0))])
        if not project:
            raise ToolError(_("Chantier %s introuvable ou non accessible à cet utilisateur.") % project_id)
        return project

    @staticmethod
    def _pct(value):
        return round(value or 0.0, 1)

    @staticmethod
    def _date(value):
        return fields.Date.to_string(value) if value else None

    def _label(self, record, field):
        return dict(record._fields[field]._description_selection(self.env)).get(record[field]) \
            if record[field] else None

    @staticmethod
    def _done(task):
        return task.state == '1_done' or (task.x_avancement_global or 0.0) >= 100

    def _money(self, project, amount):
        currency = project.currency_id or self.env.company.currency_id
        return {'montant': round(amount or 0.0, 2), 'devise': currency.name}

    def _task_info(self, task):
        info = {
            'id': task.id,
            'nom': task.name,
            'avancement_pct': self._pct(task.x_avancement_global),
            'etat': TASK_STATES.get(task.state, task.state),
            'echeance': self._date(task.date_deadline),
            'debut_prevu': self._date(task.x_date_debut_prevue),
            'fin_prevue': self._date(task.x_date_fin_prevue),
            'tache_mere': task.parent_id.name or None,
        }
        if 'construction_element_id' in task._fields and task.construction_element_id:
            element = task.construction_element_id
            info['element'] = element.name
            info['type_element'] = element.element_type_id.name or None
            info['niveau'] = element.level_id.name or None
        if 'miro_crew_id' in task._fields and task.miro_crew_id:
            info['equipe_proposee'] = task.miro_crew_id.name
        return info

    # ------------------------------------------------------------------
    # Outils
    # ------------------------------------------------------------------
    @api.model
    def find_projects(self, query):
        Project = self.env['project.project']
        domain = []
        words = [w for w in (query or '').split() if len(w) > 1]
        if words:
            fields_ = [f for f in ('name', 'partner_id.name', 'x_ville_chantier', 'x_maitre_ouvrage')
                       if f.split('.')[0] in Project._fields]
            # Chaque mot doit apparaître dans l'un des champs : « villa ivato » trouve « Villa à Ivato »
            domain = expression.AND([
                expression.OR([[(f, 'ilike', w)] for f in fields_]) for w in words])
        projects = Project.search(domain, limit=15, order='x_status, name')
        if not projects and words:
            # Nom mal orthographié : on se contente d'un des mots
            projects = Project.search(expression.OR([[('name', 'ilike', w)] for w in words]), limit=15)
        return {
            'nombre': len(projects),
            'chantiers': [{
                'id': p.id,
                'nom': p.name,
                'statut': self._label(p, 'x_status'),
                'avancement_pct': self._pct(p.x_avancement_global),
                'client': p.partner_id.name or None,
                'ville': p.x_ville_chantier or None,
                'chef_de_chantier': p.x_responsable_chantier_id.name or None,
            } for p in projects],
        }

    @api.model
    def get_project_progress(self, project_id):
        project = self._project(project_id)
        tasks = self.env['project.task'].search([('project_id', '=', project.id)])
        done = tasks.filtered(self._done)
        open_tasks = tasks - done
        started = open_tasks.filtered(lambda t: (t.x_avancement_global or 0.0) > 0)
        late = tasks.filtered('x_est_en_retard')
        roots = tasks.filtered(lambda t: not t.parent_id).sorted(lambda t: (t.sequence, t.id))
        result = {
            'chantier': project.name,
            'avancement_global_pct': self._pct(project.x_avancement_global),
            'mode_de_calcul': "moyenne de l'avancement des ouvrages (tâches racines), "
                              "chacun étant la moyenne de ses sous-tâches",
            'statut': self._label(project, 'x_status'),
            'chef_de_chantier': project.x_responsable_chantier_id.name or None,
            'debut_des_travaux': self._date(project.x_date_debut_travaux),
            'fin_prevue': self._date(project.x_date_fin_prevue),
            'taches': {
                'total': len(tasks),
                'terminees': len(done),
                'en_cours': len(started),
                'non_commencees': len(open_tasks - started),
                'en_retard': len(late),
            },
            'ouvrages': [{
                'nom': t.name,
                'avancement_pct': self._pct(t.x_avancement_global),
                'sous_taches': len(t._get_all_descendants()),
            } for t in roots[:30]],
            'couts': {
                'budget': self._money(project, project.x_budget_total),
                'cout_prevu_taches': self._money(project, project.x_cout_prevue_total),
                'cout_reel': self._money(project, project.x_cout_reel_total),
            },
        }
        if len(roots) > 30:
            result['ouvrages_non_affiches'] = len(roots) - 30
        if 'miro_planned_end' in tasks._fields:
            ends = [d for d in tasks.mapped('miro_planned_end') if d]
            if ends:
                result['fin_selon_planning'] = self._date(max(ends).date())
        return result

    @api.model
    def get_progress_by_level(self, project_id):
        project = self._project(project_id)
        Task = self.env['project.task']
        if 'construction_element_id' not in Task._fields:
            raise ToolError(_("Les éléments de construction ne sont pas gérés dans cette base."))
        phases = Task.search([('project_id', '=', project.id), ('construction_element_id', '!=', False)])
        if not phases:
            return {'chantier': project.name, 'message': "Aucune phase liée à un élément de construction."}
        groups = {}
        for task in phases:
            element = task.construction_element_id
            level = element.level_id
            key = (level.id, element.element_type_id.name or "Autre")
            group = groups.setdefault(key, {'level': level, 'phases': Task, 'elements': set()})
            group['phases'] |= task
            group['elements'].add(element.id)
        levels = {}
        for (_level_id, type_name), group in groups.items():
            level = group['level']
            phases_ = group['phases']
            done = phases_.filtered(self._done)
            row = levels.setdefault(level.id, {
                'rank': (level.elevation or 0.0, level.sequence) if level else (-1e9, 0),
                'niveau': level.name or "Sans niveau",
                'types': [], 'phases': Task,
            })
            row['phases'] |= phases_
            row['types'].append({
                'type_element': type_name,
                'elements': len(group['elements']),
                'phases': len(phases_),
                'phases_terminees': len(done),
                'avancement_moyen_pct': self._pct(sum(phases_.mapped('x_avancement_global')) / len(phases_)),
            })
        rows = []
        for row in sorted(levels.values(), key=lambda r: r['rank']):
            phases_ = row['phases']
            rows.append({
                'niveau': row['niveau'],
                'avancement_moyen_pct': self._pct(sum(phases_.mapped('x_avancement_global')) / len(phases_)),
                'phases': len(phases_),
                'phases_terminees': len(phases_.filtered(self._done)),
                'par_type': sorted(row['types'], key=lambda t: t['type_element']),
            })
        return {'chantier': project.name, 'niveaux': rows}

    @api.model
    def get_late_tasks(self, project_id):
        project = self._project(project_id)
        late = self.env['project.task'].search(
            [('project_id', '=', project.id), ('x_est_en_retard', '=', True)], order='date_deadline, id')
        today = fields.Date.context_today(self)
        rows = []
        for task in late[:25]:
            info = self._task_info(task)
            if task.date_deadline:
                info['jours_de_retard'] = (today - task.date_deadline.date()).days
            rows.append(info)
        return {'chantier': project.name, 'nombre_en_retard': len(late), 'taches': rows,
                'non_affichees': max(len(late) - 25, 0)}

    @api.model
    def search_tasks(self, project_id, query):
        project = self._project(project_id)
        Task = self.env['project.task']
        words = [w for w in (query or '').split() if w]
        searchable = ['name']
        if 'construction_element_id' in Task._fields:
            searchable += ['construction_element_id.name', 'construction_element_id.key',
                           'construction_element_id.level_id.name',
                           'construction_element_id.element_type_id.name']
        domain = [('project_id', '=', project.id)]
        for word in words:
            domain = expression.AND([domain, expression.OR([[(f, 'ilike', word)] for f in searchable])])
        tasks = Task.search(domain, limit=21, order='x_niveau_hierarchie, sequence, id')
        return {'chantier': project.name, 'resultats': [self._task_info(t) for t in tasks[:20]],
                'resultats_tronques': len(tasks) > 20}

    @api.model
    def get_material_status(self, project_id):
        project = self._project(project_id)
        if not hasattr(project, 'get_material_dashboard'):
            raise ToolError(_("Le module des besoins en matériaux n'est pas installé."))
        data = project.get_material_dashboard()
        currency = data['currency']
        kpis = data['kpis']
        keep = ('name', 'uom', 'planned', 'ordered', 'received', 'consumed', 'remaining',
                'stock', 'shortage', 'planned_cost', 'status')
        rnd = lambda v: round(v, 2) if isinstance(v, float) else v
        return {
            'chantier': project.name,
            'devise': currency.get('symbol'),
            'indicateurs': {
                'cout_prevu': rnd(kpis['planned_cost']),
                'cout_consomme': rnd(kpis['consumed_cost']),
                'nombre_de_materiaux': kpis['material_count'],
                'commande_pct': kpis['pct_ordered'],
                'recu_pct': kpis['pct_received'],
                'consomme_pct': kpis['pct_consumed'],
                'materiaux_en_rupture': kpis['shortage'],
                'materiaux_en_depassement': kpis['overrun'],
                'besoins_sans_produit': kpis['no_product'],
            },
            'legende': "planned = prévu, ordered = commandé, received = reçu, consumed = consommé, "
                       "remaining = reste à consommer, shortage = manque à commander ; "
                       "quantités dans l'unité 'uom'",
            'principaux_materiaux': [{k: rnd(m[k]) for k in keep} for m in data['materials'][:20]],
        }

    @api.model
    def get_planning_summary(self, project_id):
        project = self._project(project_id)
        Task = self.env['project.task']
        if 'miro_planned_start' not in Task._fields:
            raise ToolError(_("Le module de planning n'est pas installé."))
        phases = Task.search([('project_id', '=', project.id), ('miro_planned_start', '!=', False)])
        if not phases:
            return {'chantier': project.name,
                    'message': "Le chantier n'a pas encore été planifié (bouton « Planifier le chantier »)."}
        now = fields.Datetime.now()
        week = now + timedelta(days=7)
        current = phases.filtered(lambda t: t.miro_planned_start <= now <= (t.miro_planned_end or now)
                                  and not self._done(t))
        upcoming = phases.filtered(lambda t: now < t.miro_planned_start <= week).sorted('miro_planned_start')
        late_start = phases.filtered(lambda t: (t.miro_planned_end or now) < now and not self._done(t))
        return {
            'chantier': project.name,
            'planifie_le': fields.Datetime.to_string(project.miro_planned_on) if project.miro_planned_on else None,
            'debut_planifie': self._date(min(phases.mapped('miro_planned_start')).date()),
            'fin_planifiee': self._date(max(d for d in phases.mapped('miro_planned_end') if d).date())
            if any(phases.mapped('miro_planned_end')) else None,
            'duree_jours_ouvres': project.miro_planned_workdays,
            'phases_planifiees': len(phases),
            'cout_main_oeuvre': self._money(project, project.miro_labor_cost),
            'heures_personnes': round(project.miro_person_hours or 0.0, 1),
            'phases_en_cours_selon_planning': [self._task_info(t) for t in current[:8]],
            'phases_qui_demarrent_sous_7_jours': [self._task_info(t) for t in upcoming[:8]],
            'phases_dont_la_fin_planifiee_est_passee': len(late_start),
            'remarques': (project.miro_planning_warnings or '')[:1500] or None,
        }
