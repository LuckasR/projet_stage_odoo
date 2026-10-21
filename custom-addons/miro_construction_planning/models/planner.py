"""Planning du chantier : chaque phase placée dans le temps à partir de la
date de début des travaux.

Ordonnancement en série (« serial schedule generation ») :

  1. les phases sont prises dans l'ordre de la structure — fondations,
     poteaux du RDC, poutres, dalle, poteaux de l'étage... (cf. GROUP_*) —
     et, dans un élément, dans l'ordre du gabarit ;
  2. chacune démarre au plus tôt après : la date de début du chantier, la fin
     de la phase dont elle dépend (+ le délai technique : décoffrage 7 j après
     le coulage), la fin des groupes d'éléments qui la précèdent ;
  3. et seulement quand une équipe de son type est libre : à aucun moment
     plus d'équipes d'un même type ne travaillent en parallèle que le
     chantier n'en prévoit (1 par défaut, réglable par équipe).

Le planning est une PROPOSITION : il ne dépend pas des employés saisis.
Il en déduit l'effectif à prévoir par métier ; le chef de chantier affecte
ensuite les ouvriers au démarrage des travaux.

Le temps est découpé en quarts d'heure ouvrés du calendrier du chantier
(jours fériés et congés du calendrier compris) : une phase de 6 h commencée
à 15 h se termine le lendemain à 13 h. Un délai technique court en jours
calendaires (le béton sèche aussi le dimanche).
"""
import bisect
import math
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo.addons.miro_construction_project.service.footing_detection_service import is_ground_slab

SLOT = timedelta(minutes=15)
SLOTS_PER_HOUR = 4

# Classes d'éléments et enchaînement de la structure
FOUNDATION_TYPES = ('semelle', 'semelle_filante', 'longrine')
CLASS_ORDER = {'fondation': 0, 'dallage': 1, 'poteau': 2, 'poutre': 3,
               'dalle': 4, 'mur': 5, 'autre': 6}


def element_class(element):
    code = element.element_type_id.code or ''
    if code in FOUNDATION_TYPES:
        return 'fondation'
    if code == 'dalle':
        return 'dallage' if is_ground_slab(element.key) else 'dalle'
    if code in ('poteau', 'poutre', 'mur'):
        return code
    return 'autre'


class WorkTime:
    """Quarts d'heure ouvrés du calendrier, à partir d'une date."""

    def __init__(self, calendar, start_date):
        self.calendar = calendar
        self.tz = pytz.timezone(calendar.tz or 'UTC')
        self.start = self.tz.localize(datetime.combine(start_date, time.min))
        self.slots = []
        self.horizon = self.start
        self._extend()

    def _extend(self, days=370):
        until = self.horizon + timedelta(days=days)
        intervals = self.calendar._work_intervals_batch(self.horizon, until)[False]
        for begin, stop, _rec in intervals:
            t = begin
            while t + SLOT <= stop:
                self.slots.append(t)
                t += SLOT
        self.horizon = until
        if not self.slots:
            raise ValueError("Le calendrier de travail n'a aucune heure ouvrée.")

    def slot(self, index):
        while index >= len(self.slots):
            self._extend()
        return self.slots[index]

    def first_slot_from(self, moment):
        """Premier quart d'heure ouvré commençant à `moment` ou après."""
        while self.slots[-1] < moment:
            self._extend()
        return bisect.bisect_left(self.slots, moment)

    def end_of(self, index):
        return self.slot(index) + SLOT


class SitePlanner:
    """Planifie les phases d'un chantier ; ne touche pas à la base : le
    résultat est lu par project.project._miro_apply_plan."""

    def __init__(self, project, start_date):
        self.project = project
        self.env = project.env
        calendar = project.miro_calendar_id or project.resource_calendar_id \
            or self.env.company.resource_calendar_id
        self.work = WorkTime(calendar, start_date)
        self.hours_per_day = project.company_id.miro_hours_per_day or 8.0
        self.warnings = []
        self.usage = defaultdict(lambda: defaultdict(int))   # équipe -> quart d'heure -> équipes
        self.default_parallel = max(project.miro_parallel_crews or 1, 1)
        self.parallel = {line.crew_id: max(line.count, 1) for line in project.miro_crew_capacity_ids}
        self.result = {}                                      # tâche -> (début, fin) aware

    # ------------------------------------------------------------------
    def run(self):
        phases = self.env['project.task'].search([
            ('project_id', '=', self.project.id),
            ('construction_element_id', '!=', False),
            ('phase_template_line_id', '!=', False)])
        todo = phases.filtered(lambda t: not self._is_finished(t))
        if not todo:
            return self.result
        groups = self._groups(todo)
        order = self._group_order(groups)
        group_end = {}
        for key in order:
            ready = max([group_end[p] for p in self._prerequisites(key, groups) if p in group_end]
                        or [self.work.start])
            ends = []
            for element in sorted(groups[key], key=lambda e: (e.key or e.name or '', e.id)):
                ends.extend(self._plan_element(element, todo, ready))
            group_end[key] = max(ends) if ends else ready
        return self.result

    @staticmethod
    def _is_finished(task):
        return task.state in ('1_done', '1_canceled') or (task.x_avancement_global or 0) >= 100

    # ------------------------------------------------------------------
    # Groupes d'éléments et leur enchaînement
    # ------------------------------------------------------------------
    def _groups(self, tasks):
        groups = defaultdict(lambda: self.env['construction.element'])
        for element in tasks.construction_element_id:
            groups[(element_class(element), element.level_id.id or 0)] |= element
        return groups

    def _level_rank(self, level_id):
        """Rang d'un niveau : altitude, puis séquence ; sans niveau, tout en bas."""
        if not level_id:
            return (-1e9, 0)
        level = self.env['construction.plan.level'].browse(level_id)
        return (level.elevation or 0.0, level.sequence)

    def _group_order(self, groups):
        # Les fondations passent avant tout, quel que soit leur niveau
        def key(group):
            cls, level = group
            rank = (-1e10, 0) if cls == 'fondation' else self._level_rank(level)
            return (rank, CLASS_ORDER[cls])
        return sorted(groups, key=key)

    def _prerequisites(self, key, groups):
        cls, level = key
        same = lambda c: [g for g in groups if g == (c, level)]
        foundations = [g for g in groups if g[0] == 'fondation']
        if cls in ('fondation', 'autre'):
            return []
        if cls == 'dallage':
            return foundations
        if cls == 'poteau':
            below = [g for g in groups if g[0] == 'dalle'
                     and self._level_rank(g[1]) < self._level_rank(level)]
            if below:
                top = max(below, key=lambda g: self._level_rank(g[1]))
                return [top]
            return foundations
        if cls == 'poutre':
            return same('poteau') or self._prerequisites(('poteau', level), groups)
        if cls == 'dalle':
            return same('poutre') or same('poteau') or self._prerequisites(('poteau', level), groups)
        if cls == 'mur':
            return same('poteau')
        return []

    # ------------------------------------------------------------------
    # Phases d'un élément
    # ------------------------------------------------------------------
    def _plan_element(self, element, todo, ready):
        phases = todo.filtered(lambda t: t.construction_element_id == element) \
            .sorted(lambda t: (t.phase_template_line_id.sequence, t.id))
        all_phases = element.task_ids.filtered('phase_template_line_id')
        ends = []
        previous = None
        for task in phases:
            line = task.phase_template_line_id
            earliest = ready
            pred = all_phases.filtered(lambda t: t.phase_template_line_id == line.depends_on_line_id)[:1] \
                if line.depends_on_line_id else previous
            if pred and pred in self.result:
                earliest = max(earliest, self.result[pred][1] + timedelta(days=line.min_lag_days or 0.0))
            start, end = self._place(task, earliest)
            self.result[task] = (start, end)
            ends.append(end)
            previous = task
        return ends

    def _crew_capacity(self, crew):
        """Nombre d'équipes de ce type pouvant travailler en même temps."""
        return self.parallel.get(crew, self.default_parallel)

    def _warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    def _place(self, task, earliest):
        """Premier créneau où l'équipe de la phase est disponible pendant
        toute sa durée."""
        hours = task.miro_duration_hours or 0.0
        progress = min(max(task.x_avancement_global or 0.0, 0.0), 100.0)
        hours *= (1 - progress / 100.0)
        length = math.ceil(hours * SLOTS_PER_HOUR - 1e-9)
        first = self.work.first_slot_from(earliest)
        if length <= 0:
            moment = self.work.slot(first)
            return moment, moment
        crew = task.miro_crew_id
        if not crew:
            # Sans équipe (pas de cadence) : durée sans contrainte d'équipe
            return self.work.slot(first), self.work.end_of(first + length - 1)
        cap = self._crew_capacity(crew)
        usage = self.usage[crew]
        s = first
        while True:
            clash = next((k for k in range(s, s + length) if usage[k] + 1 > cap), None)
            if clash is None:
                break
            s = clash + 1
        for k in range(s, s + length):
            usage[k] += 1
        return self.work.slot(s), self.work.end_of(s + length - 1)

    # ------------------------------------------------------------------
    # Charge par métier
    # ------------------------------------------------------------------
    def daily_load(self):
        """{(jour, métier): (pointe de personnes, heures-personnes)} sur les
        phases planifiées, toutes équipes confondues (métiers illimités
        compris)."""
        per_slot = defaultdict(lambda: defaultdict(int))
        for task, (start, end) in self.result.items():
            if start == end:
                continue
            first = self.work.first_slot_from(start)
            last = self.work.first_slot_from(end)
            for line in task.miro_crew_id.line_ids:
                for k in range(first, last):
                    per_slot[line.trade_id][k] += line.quantity
        load = {}
        for trade, slots in per_slot.items():
            for k, persons in slots.items():
                day = self.work.slot(k).date()
                peak, hours = load.get((day, trade), (0, 0.0))
                load[(day, trade)] = (max(peak, persons), hours + persons / SLOTS_PER_HOUR)
        return load
