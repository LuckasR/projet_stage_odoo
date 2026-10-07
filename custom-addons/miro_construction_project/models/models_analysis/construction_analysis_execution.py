import base64
import json
import logging
import statistics
import tempfile
from pathlib import Path

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ...service.detail_analysis_service import DetailAnalysisService
from ...service.formwork_detection_service import (
    FORMWORK_LAYERS,
    TYPE_WALL,
    WALL_LAYERS,
    FormworkDetectionService,
)
from ...service.plan_analysis import PlanContext, normalize_text
from .construction_analysis_footing import UNIT_TO_M

_logger = logging.getLogger(__name__)

# Ce que le profil structurel du plan de détail sait donner, par type
# d'ouvrage : clé de dimension -> (ouvrage du profil, dimension). Une cote
# déjà relevée sur le plan n'est jamais remplacée.
PROFILE_SECTIONS = {
    'poteau': {'l': ('poteau', 'w'), 'w': ('poteau', 'w')},
    'poutre': {'w': ('poutre', 'w'), 'h': ('poutre', 'h')},
    'dalle': {'h': ('dalle', 'h')},
    'semelle': {'h': ('semelle', 'h')},
    'semelle_filante': {'w': ('semelle_filante', 'w'), 'h': ('semelle_filante', 'h')},
    'longrine': {'w': ('longrine', 'w'), 'h': ('longrine', 'h')},
}
# Ouvrages qui montent d'un plancher au suivant : hauteur libre de l'étage
STOREY_HEIGHT_TYPES = ('poteau', 'mur')
# Un mur du coffrage est le même qu'un mur déjà connu du niveau (relevé sur
# l'architecture, par exemple) si leurs axes sont à moins de ça (m)
SAME_WALL_TOLERANCE = 0.05
# En deçà, un mur est une cloison
PARTITION_MAX_THICKNESS = 0.15
# Une ouverture du coffrage est la même qu'une ouverture déjà connue si leurs
# centres sont à moins de ça (m) et leurs largeurs proches
SAME_OPENING_TOLERANCE = 0.30
SAME_OPENING_WIDTH_TOLERANCE = 0.10
# Mots d'une anomalie levée par la cote qu'on vient de compléter
ISSUE_WORDS = {'h': ('hauteur', 'epaisseur'), 'w': ('largeur',)}


class ConstructionAnalysisExecution(models.Model):
    """Moteurs des plans d'EXÉCUTION de structure.

    « Coffrage » lit poteaux, poutres, dalles et murs d'un plan de coffrage
    et les fait entrer dans le circuit commun :

        plan -> CE MOTEUR -> brouillons -> validation -> éléments -> phases

    « Coupes et détails » ne crée aucun brouillon : ses coupes redessinent
    les ouvrages du coffrage. Il produit un PROFIL STRUCTUREL (hauteurs
    d'étage, épaisseurs de plancher, sections, ferraillage) qui complète les
    brouillons en attente du projet — ceux déjà là comme ceux des plans
    importés après lui. L'ordre d'import des plans est donc indifférent.

    Importé après les autres moteurs (cf. __init__.py) : son aiguillage doit
    être le plus extérieur."""
    _inherit = 'construction.analysis'

    engine = fields.Selection(
        selection_add=[('formwork', "Coffrage (poteaux, poutres, dalles, murs)"),
                       ('details', "Coupes et détails (profil structurel)")],
        ondelete={'formwork': 'cascade', 'details': 'cascade'})
    plan_warnings = fields.Text(
        "Anomalies signalées par le plan", readonly=True,
        help="Non-conformités écrites SUR le plan (calque X-HYP, mentions "
             "« NON CONFORME »). L'analyse a réussi : c'est le projet qui est "
             "à revoir, pas la lecture du plan.")
    completed_draft_count = fields.Integer(
        "Brouillons complétés", readonly=True,
        help="Brouillons en attente du projet dont une cote ou le ferraillage "
             "a été complété par ce plan de détail.")
    profile_summary = fields.Text(
        "Profil structurel", compute='_compute_profile_summary',
        help="Ce que le plan de détail a relevé : il complète les brouillons "
             "en attente du projet.")

    @api.depends('result_json', 'engine')
    def _compute_profile_summary(self):
        for rec in self:
            profile = rec._profile() if rec.engine == 'details' else None
            rec.profile_summary = rec._format_profile(profile) if profile else False

    def _job_run_analysis(self):
        """Le message générique (« N brouillon(s) créés ») ne dit rien d'un
        plan de détail, qui n'en crée jamais : on dit ce qu'il a complété."""
        res = super()._job_run_analysis()
        if self.engine != 'details' or self.state != 'done':
            return res
        message = _("Profil structurel relevé : %d brouillon(s) en attente complété(s).") \
            % self.completed_draft_count
        if self.plan_warnings:
            message += " " + _("%d anomalie(s) signalée(s) par le plan.") \
                % len(self.plan_warnings.splitlines())
        return message

    # ------------------------------------------------------------------
    # Lecture du plan
    # ------------------------------------------------------------------
    def _analyze_plan(self):
        self.ensure_one()
        if self.manual_json or self.engine not in ('formwork', 'details'):
            return super()._analyze_plan()

        dwg = self.file_id
        if not dwg.dxf_file:
            raise UserError(_(
                "Aucun fichier DXF disponible pour ce plan. Traitez-le d'abord "
                "(bouton « Traiter / Convertir »)."))

        meta = dwg.metadata_id[:1]
        unit_scale = UNIT_TO_M.get(meta.units_code, 1.0) if meta else 1.0

        if self.engine == 'formwork':
            service = self._load_service(
                dwg, lambda path: FormworkDetectionService(
                    path, context=self._plan_context(dwg), unit_scale=unit_scale))
            items = service.detect()
            if not items:
                raise ValidationError(_(
                    "Aucun ouvrage détecté sur ce plan de coffrage. Vérifiez que "
                    "les ouvrages sont dessinés sur les calques %s et que le plan "
                    "est classé en vue « Plan ».") % ", ".join(FORMWORK_LAYERS))
            return self._formwork_result(service, items, unit_scale)

        service = self._load_service(
            dwg, lambda path: DetailAnalysisService(path, unit_scale=unit_scale))
        profile = service.analyze()
        if not (profile.get('storeys') or profile.get('sections')
                or profile.get('reinforcement')):
            raise ValidationError(_(
                "Rien d'exploitable sur ce plan de détail : aucune coupe calée "
                "(repères de niveau S-NIV), aucun détail « Dn - ... » à "
                "l'échelle connue, aucun tableau de ferraillage."))
        return service.to_analysis_result(profile)

    def _formwork_result(self, service, items, unit_scale):
        """Résultat du coffrage. Un mur n'est pas un simple brouillon : il
        devient d'abord un objet construction.wall — c'est lui qui porte la
        géométrie et reçoit la hauteur du plan de détail — et son brouillon
        en est tiré par `_wall_to_item`, exactement comme pour le moteur
        « murs ». Le lien mur -> brouillon -> élément tient alors tout seul :
        une hauteur écrite sur le mur est reportée par `_sync_elements`."""
        walls, openings = self._upsert_formwork_walls(
            [i for i in items if i.type_code == TYPE_WALL], unit_scale)

        profile_analysis = self._latest_profile_analysis()
        if profile_analysis:
            self._apply_profile_to_walls(walls, profile_analysis._profile())

        if self.project_id:
            # Les ouvertures d'autres plans (architecture...) trouvent elles
            # aussi leur mur parmi ceux que le coffrage vient d'apporter.
            openings._link_host_walls(self.project_id)
            if profile_analysis:
                # Hauteurs, allèges et natures lues dans les coupes du plan
                # de détail déjà importé.
                self._apply_profile_openings(self.project_id, profile_analysis._profile())

        elements = [i.to_analysis_item() for i in items if i.type_code != TYPE_WALL]
        for wall in walls:
            item = self._wall_to_item(wall)
            item['issue'] = " ; ".join(filter(None, [
                _("Mur relevé sur le fond de plan du coffrage (%s) : à confirmer")
                % wall.layer, item.get('issue')]))
            elements.append(item)
        for opening in openings:
            item = self._opening_to_item(opening)
            if opening.opening_type == 'unknown':
                item['issue'] = " ; ".join(filter(None, [
                    _("Nature à confirmer (porte ou fenêtre) : le coffrage ne "
                      "montre qu'une interruption du mur %s") % opening.wall_id.name,
                    item.get('issue')]))
            elements.append(item)
        return {'schema_version': 1, 'elements': elements}

    def _upsert_formwork_openings(self, wall, gaps, unit_scale):
        """Baies d'un mur du coffrage -> construction.opening reliées à ce mur.

        Une ouverture déjà connue au même endroit (relance, plan
        d'architecture qui en donne la nature) est reprise et complétée,
        jamais réécrite. Sur le seul coffrage, la nature d'une baie n'est pas
        lisible : celle d'une cloison est une porte intérieure, les autres
        restent « inconnue » jusqu'à confirmation."""
        self.ensure_one()
        Opening = self.env['construction.opening']
        dwg = self.file_id
        level = dwg.level_ids[:1]
        view = dwg.view_ids[:1]
        context = self._plan_context(dwg)
        domain = ([('project_id', '=', dwg.project_id.id)] if dwg.project_id
                  else [('dwg_file_id', '=', dwg.id)])
        known = Opening.search(domain + [('level_id', '=', level.id or False)])
        partition = wall.wall_type == 'partition'

        traceability = {'source_file_ids': [Command.link(dwg.id)]}
        if view:
            traceability['source_view_ids'] = [Command.link(view.id)]

        found = Opening
        for x1, y1, x2, y2 in gaps:
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            width = round(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 * unit_scale, 3)
            match_key = context.match_key("ouv-ref-%.2f-%.2f" % (cx, cy))
            opening = (known.filtered(lambda o, k=match_key: o.match_key == k)[:1]
                       or self._same_opening(known, cx, cy, width, unit_scale))
            if opening:
                vals = dict(traceability, wall_id=wall.id)
                if not opening.width:
                    vals['width'] = width
                if not opening.thickness:
                    vals['thickness'] = wall.thickness
                if not opening._has_axis():
                    vals.update(start_x=x1, start_y=y1, end_x=x2, end_y=y2,
                                center_x=cx, center_y=cy)
                opening.write(vals)
            else:
                opening = Opening.create(dict(
                    traceability,
                    name=_("Baie %s") % match_key.split('|')[-1],
                    dwg_file_id=dwg.id,
                    level_id=level.id or False,
                    wall_id=wall.id,
                    match_key=match_key,
                    layer=wall.layer,
                    opening_type='door' if partition else 'unknown',
                    wall_position='interior' if partition else 'unknown',
                    start_x=x1, start_y=y1, end_x=x2, end_y=y2,
                    center_x=cx, center_y=cy,
                    width=width, thickness=wall.thickness,
                    detection_method='geometry',
                    confidence=55.0,
                ))
                known |= opening
            found |= opening
        return found

    @staticmethod
    def _same_opening(openings, cx, cy, width, unit_scale):
        tolerance = SAME_OPENING_TOLERANCE / (unit_scale or 1.0)
        for opening in openings:
            if not opening._has_axis():
                continue
            distance = ((opening.center_x - cx) ** 2 + (opening.center_y - cy) ** 2) ** 0.5
            if distance <= tolerance and (
                    not opening.width
                    or abs(opening.width - width) <= SAME_OPENING_WIDTH_TOLERANCE):
                return opening
        return openings.browse()

    def _upsert_formwork_walls(self, detected, unit_scale):
        """Crée les murs du coffrage, ou retrouve ceux déjà connus du niveau :
        par leur clé (relance de l'analyse), sinon par leur position (mur
        déjà relevé sur un autre plan). Un mur existant n'est que complété,
        jamais réécrit, et rien n'est jamais supprimé. Ses baies deviennent
        des ouvertures rattachées à lui. Retourne (murs, ouvertures)."""
        self.ensure_one()
        Wall = self.env['construction.wall']
        dwg = self.file_id
        level = dwg.level_ids[:1]
        view = dwg.view_ids[:1]
        context = self._plan_context(dwg)
        domain = ([('project_id', '=', dwg.project_id.id)] if dwg.project_id
                  else [('dwg_file_id', '=', dwg.id)])
        known = Wall.search(domain + [('level_id', '=', level.id or False)])

        traceability = {'source_file_ids': [Command.link(dwg.id)]}
        if view:
            traceability['source_view_ids'] = [Command.link(view.id)]

        walls = Wall
        openings = self.env['construction.opening']
        for item in detected:
            x1, y1, x2, y2 = item.axis
            length = round(item.dimensions['l'], 3)
            thickness = round(item.dimensions['ep'], 3)
            match_key = context.match_key(
                "ref-axe-%.2f-%.2f" % (item.center_x, item.center_y))
            wall = (known.filtered(lambda w, k=match_key: w.match_key == k)[:1]
                    or self._same_wall(known, item, unit_scale))
            if wall:
                vals = dict(traceability)
                if not wall.length:
                    vals['length'] = length
                if not wall.thickness:
                    vals['thickness'] = thickness
                wall.write(vals)
            else:
                wall = Wall.create(dict(
                    traceability,
                    name=_("Mur %s") % match_key.split('|')[-1],
                    dwg_file_id=dwg.id,
                    level_id=level.id or False,
                    match_key=match_key,
                    layer=WALL_LAYERS[0],
                    wall_type=('partition' if thickness <= PARTITION_MAX_THICKNESS
                               else 'unknown'),
                    geometry_type='line_pair',
                    detection_method='layer',
                    start_x=x1, start_y=y1, end_x=x2, end_y=y2,
                    center_x=item.center_x, center_y=item.center_y,
                    length=length, thickness=thickness,
                    confidence=round(item.confidence * 100, 2),
                ))
                known |= wall
            walls |= wall
            openings |= self._upsert_formwork_openings(wall, item.openings, unit_scale)
        _logger.info("%s : %d mur(s) et %d ouverture(s) du coffrage",
                     dwg.filename, len(walls), len(openings))
        return walls, openings

    @staticmethod
    def _same_wall(walls, item, unit_scale):
        """Mur déjà connu dont l'axe porte celui détecté : même direction,
        même épaisseur, centre détecté sur son axe."""
        x1, y1, x2, y2 = item.axis
        dx, dy = x2 - x1, y2 - y1
        norm = (dx * dx + dy * dy) ** 0.5 or 1.0
        tolerance = SAME_WALL_TOLERANCE / (unit_scale or 1.0)
        for wall in walls:
            wx, wy = wall.end_x - wall.start_x, wall.end_y - wall.start_y
            wlen = (wx * wx + wy * wy) ** 0.5
            if not wlen or abs(wall.thickness - item.dimensions['ep']) > 0.02:
                continue
            if abs(dx * wy - dy * wx) / (norm * wlen) > 0.035:   # ~2°
                continue
            px, py = item.center_x - wall.start_x, item.center_y - wall.start_y
            along = (px * wx + py * wy) / wlen
            offset = abs(px * wy - py * wx) / wlen
            if offset <= tolerance and -tolerance <= along <= wlen + tolerance:
                return wall
        return walls.browse()

    @api.model
    def _apply_profile_to_walls(self, walls, profile):
        """Hauteur libre de l'étage, sur les murs qui n'en ont pas encore.
        L'écriture déclenche construction.wall._sync_elements : brouillons
        et éléments liés reçoivent hauteur et métrés."""
        completed = walls.browse()
        for wall in walls.filtered(lambda w: not w.height):
            storey = self._storey_for_level(profile, wall.level_id)
            if storey and storey.get('clear_height'):
                wall.height = storey['clear_height']
                completed |= wall
        return completed

    # ------------------------------------------------------------------
    # Ouvertures lues dans les coupes du plan de détail
    # ------------------------------------------------------------------
    @api.model
    def _level_for_storey(self, index):
        """Niveau de l'étage n° `index` des coupes (0 = rez-de-chaussée)."""
        levels = self.env['construction.plan.level'].search([], order='sequence, id')
        ground = levels.filtered(
            lambda l: (l.code or '').strip().upper() == 'RDC'
            or 'rez' in normalize_text(l.name))[:1]
        if not ground:
            return levels.browse()
        position = list(levels).index(ground) + index
        return levels[position] if 0 <= position < len(levels) else levels.browse()

    @api.model
    def _apply_profile_openings(self, project, profile):
        """Complète les ouvertures du projet avec celles des coupes : hauteur
        et allège (jamais réécrites si déjà connues), nature et repère.
        L'ouverture est retrouvée par son repère, sinon par sa position :
        coupe « A-A à Y = 2.20 », à 0,15 m du nu extérieur gauche. Écrire
        sa hauteur recalcule la surface nette de son mur.
        Retourne (ouvertures complétées, repères non retrouvés)."""
        Opening = self.env['construction.opening']
        Wall = self.env['construction.wall']
        completed, unmatched = Opening, []
        for item in profile.get('openings') or []:
            level = self._level_for_storey(item.get('storey') or 0)
            if not level:
                unmatched.append(item)
                continue
            domain = [('project_id', '=', project.id), ('level_id', '=', level.id)]
            candidates = Opening.search(domain)
            opening = (item.get('mark') and candidates.filtered(
                lambda o, m=item['mark']: (o.mark or '').upper() == m)[:1])
            if not opening:
                opening = self._opening_at_cut(candidates, Wall.search(domain), item)
            if not opening:
                unmatched.append(item)
                continue

            vals = {}
            if not opening.height and item.get('height'):
                vals.update(height=item['height'], sill_height=item.get('sill') or 0.0)
            # La nature d'une baie du coffrage n'était qu'une supposition
            # (cloison -> porte) : le repère du plan la remplace.
            guessed = 'ouv-ref-' in (opening.match_key or '')
            if item.get('type') and item['type'] != opening.opening_type and (
                    opening.opening_type == 'unknown' or guessed):
                vals['opening_type'] = item['type']
            if item.get('mark') and not opening.mark:
                vals['mark'] = item['mark']
            if vals:
                opening.write(vals)
                completed |= opening
        return completed, unmatched

    @staticmethod
    def _opening_at_cut(openings, walls, item):
        """Ouverture coupée par une coupe, retrouvée sur le plan.

        L'emprise extérieure du bâtiment vient des murs du niveau (nus
        extérieurs). La coupe « Y = 2.20 » est la droite y = ymin + 2.20 ;
        l'ouverture est à `offset` du nu gauche le long de cette droite. Le
        sens de lecture d'une coupe n'étant pas toujours le même, l'autre
        sens est essayé si le premier ne tombe sur aucune ouverture."""
        if not item.get('cut_axis') or not walls or not openings:
            return openings.browse()
        xs, ys, factors = [], [], []
        for wall in walls:
            dx, dy = wall.end_x - wall.start_x, wall.end_y - wall.start_y
            length = (dx * dx + dy * dy) ** 0.5
            if not length:
                continue
            factor = (wall.length / length) if wall.length else 1.0
            factors.append(factor)
            half = (wall.thickness or 0.0) / factor / 2.0
            if abs(dx) < abs(dy):
                xs += [wall.start_x - half, wall.start_x + half]
            else:
                ys += [wall.start_y - half, wall.start_y + half]
        if not (xs and ys):
            return openings.browse()
        factor = statistics.median(factors)
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        cut, offset = item['cut_value'] / factor, item['offset'] / factor
        if item['cut_axis'] == 'Y':
            points = [(minx + offset, miny + cut), (maxx - offset, miny + cut)]
        else:
            points = [(minx + cut, miny + offset), (minx + cut, maxy - offset)]

        for px, py in points:
            best, best_distance = None, None
            for opening in openings.filtered(lambda o: o._has_axis()):
                sx, sy, ex, ey = opening.start_x, opening.start_y, opening.end_x, opening.end_y
                vx, vy = ex - sx, ey - sy
                t = max(0.0, min(1.0, ((px - sx) * vx + (py - sy) * vy) / (vx * vx + vy * vy)))
                distance = ((sx + t * vx - px) ** 2 + (sy + t * vy - py) ** 2) ** 0.5
                thickness = opening.thickness or opening.wall_id.thickness or 0.30
                if distance <= (thickness / 2.0 + 0.05) / factor and (
                        best_distance is None or distance < best_distance):
                    best, best_distance = opening, distance
            if best:
                return best
        return openings.browse()

    @api.model
    def _storey_for_level(self, profile, level):
        """Étage du profil correspondant à un niveau : par son altitude si
        elle est renseignée, sinon par son rang par rapport au
        rez-de-chaussée (étage 0 du profil)."""
        storeys = profile.get('storeys') or []
        if not storeys or not level:
            return None
        if level.elevation:
            for storey in storeys:
                if abs(level.elevation - storey.get('floor', 0.0)) < 0.05:
                    return storey
        levels = self.env['construction.plan.level'].search([], order='sequence, id')
        ground = levels.filtered(
            lambda l: (l.code or '').strip().upper() == 'RDC'
            or 'rez' in normalize_text(l.name))[:1]
        if not ground or level not in levels:
            return None
        rank = list(levels).index(level) - list(levels).index(ground)
        return next((s for s in storeys if s.get('index') == rank), None)

    @staticmethod
    def _load_service(dwg, factory):
        """Instancie le service sur une copie temporaire du DXF : ezdxf
        charge le document à la construction, le fichier peut ensuite
        disparaître."""
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(base64.b64decode(dwg.dxf_file))
            tmp_path = tmp.name
        try:
            return factory(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @staticmethod
    def _plan_context(dwg):
        level = dwg.level_ids[:1]
        view = dwg.view_ids[:1]
        return PlanContext.build(
            view=view.code or view.name,
            level=level.code or level.name,
            level_label=level.name,
            plan_types=[t.code or t.name for t in dwg.plan_type_ids],
            title=dwg.filename,
        )

    # ------------------------------------------------------------------
    # Résultat
    # ------------------------------------------------------------------
    def _process_result(self, data):
        self.ensure_one()
        if self.engine == 'details':
            return self._process_profile(data)

        res = super()._process_result(data)
        # Un plan de détail déjà importé complète les brouillons de ce plan.
        profile_analysis = self._latest_profile_analysis()
        if profile_analysis:
            completed = self.draft_ids.filtered(
                lambda d: d.state == 'pending')._apply_structure_profile(
                    profile_analysis._profile(), profile_analysis.file_id.display_name)
            if completed:
                self.message_post(body=_(
                    "%d brouillon(s) complété(s) par le plan de détail « %s ».")
                    % (len(completed), profile_analysis.file_id.display_name))
        if self.engine == 'formwork':
            # Le coffrage donne souvent toutes les cotes (nomenclature) :
            # l'acier se déduit alors du ratio du type, sans rien inventer.
            self.draft_ids.filtered(
                lambda d: d.state == 'pending')._compute_quantities(apply_defaults=False)
        return res

    def _process_profile(self, data):
        profile = data.get('profile') if isinstance(data, dict) else None
        if not isinstance(profile, dict):
            raise ValidationError(_("Le résultat d'un plan de détail doit porter "
                                    "un objet « profile »."))
        warnings = profile.get('warnings') or []
        completed = self.env['construction.element.draft']
        walls = self.env['construction.wall']
        openings, unmatched = self.env['construction.opening'], []
        if self.project_id:
            # Les murs d'abord : leur hauteur se propage d'elle-même à leurs
            # brouillons et éléments (cf. construction.wall._sync_elements).
            walls = self._apply_profile_to_walls(self.env['construction.wall'].search([
                ('project_id', '=', self.project_id.id)]), profile)
            pending = self.env['construction.element.draft'].search([
                ('project_id', '=', self.project_id.id), ('state', '=', 'pending')])
            completed = pending._apply_structure_profile(
                profile, self.file_id.display_name)
            completed |= walls.draft_ids.filtered(lambda d: d.state == 'pending')
            openings, unmatched = self._apply_profile_openings(self.project_id, profile)
            completed |= openings.draft_ids.filtered(lambda d: d.state == 'pending')

        # Les anomalies du PLAN ne vont pas dans le journal d'erreur : la
        # lecture a réussi, elles le feraient passer pour un échec.
        self.write({
            'state': 'done',
            'finished_at': fields.Datetime.now(),
            'error_log': False,
            'plan_warnings': "\n".join(warnings) or False,
            'completed_draft_count': len(completed),
        })

        body = _("Profil structurel relevé. %d brouillon(s) en attente complété(s), "
                 "%d mur(s) ont reçu leur hauteur, %d ouverture(s) leur hauteur, "
                 "allège et nature.") % (len(completed), len(walls), len(openings))
        if unmatched:
            body += " " + _(
                "Ouvertures des coupes sans correspondance sur les plans du "
                "projet (leur plan de coffrage n'est peut-être pas encore "
                "importé ; elles seront complétées à son import) : %s.") % ", ".join(
                    o.get('mark') or "?" for o in unmatched)
        if not completed:
            body += " " + _(
                "Aucun brouillon en attente dans ce projet pour l'instant : les "
                "plans de coffrage et de fondation importés ensuite seront "
                "complétés automatiquement.")
        if warnings:
            body += "<br/>" + _("Anomalies signalées par le plan :") + "<br/>- " + \
                "<br/>- ".join(warnings)
        self.message_post(body=body)

    def _latest_profile_analysis(self):
        self.ensure_one()
        if not self.project_id:
            return self.browse()
        return self.search([
            ('project_id', '=', self.project_id.id),
            ('engine', '=', 'details'),
            ('state', '=', 'done'),
        ], order='finished_at desc, id desc', limit=1)

    def _profile(self):
        self.ensure_one()
        try:
            return (json.loads(self.result_json or '{}') or {}).get('profile') or {}
        except ValueError:
            return {}

    @api.model
    def _format_profile(self, profile):
        lines = []
        for st in profile.get('storeys') or []:
            lines.append(_("Étage %(i)s : sol %(f)+.2f, sous-face %(c)+.2f, "
                           "hauteur libre %(h).2f m, plancher %(e).2f m") % {
                'i': st.get('index'), 'f': st.get('floor', 0.0),
                'c': st.get('ceiling', 0.0), 'h': st.get('clear_height', 0.0),
                'e': st.get('slab_thickness', 0.0)})
        ground = profile.get('ground_slab')
        if ground:
            lines.append(_("Dallage : %.2f m") % ground.get('thickness', 0.0))
        for type_code, dims in sorted((profile.get('sections') or {}).items()):
            lines.append(_("Section %s : %s") % (type_code, ", ".join(
                "%s=%.2f m" % kv for kv in sorted(dims.items()))))
        labels = {'window': _("fenêtre"), 'door': _("porte"), 'bay': _("baie"),
                  'french_window': _("porte-fenêtre"), 'garage_door': _("porte de garage")}
        for o in profile.get('openings') or []:
            lines.append(_("Ouverture %(m)s (étage %(s)s, coupe %(c)s) : %(t)s, "
                           "hauteur %(h).2f m, allège %(a).2f m") % {
                'm': o.get('mark') or "?", 's': o.get('storey'),
                'c': o.get('section') or "?", 't': labels.get(o.get('type'), "?"),
                'h': o.get('height') or 0.0, 'a': o.get('sill') or 0.0})
        for type_code, desc in sorted((profile.get('reinforcement') or {}).items()):
            lines.append(_("Ferraillage %s : %s") % (type_code, desc))
        for warning in profile.get('warnings') or []:
            lines.append(_("⚠ %s") % warning)
        return "\n".join(lines)


class ConstructionElementDraftProfile(models.Model):
    _inherit = 'construction.element.draft'

    def _profile_storey(self, profile):
        self.ensure_one()
        return self.env['construction.analysis']._storey_for_level(profile, self.level_id)

    def _apply_structure_profile(self, profile, source):
        """Complète les cotes manquantes et le ferraillage à partir du profil
        d'un plan de détail, puis chiffre ce qui devient chiffrable. Retourne
        les brouillons modifiés."""
        sections = profile.get('sections') or {}
        reinforcements = profile.get('reinforcement') or {}
        completed = self.browse()

        for rec in self:
            code = rec.type_id.code or rec.type_code
            dims = dict(rec.dimensions or {})
            filled = {}

            def fill(key, value, dims=dims, filled=filled):
                if value and not dims.get(key):
                    dims[key] = round(value, 3)
                    filled[key] = value

            storey = rec._profile_storey(profile)
            # Un mur relié à son objet construction.wall reçoit sa hauteur
            # par le mur (cf. _apply_profile_to_walls), pas ici.
            if storey and code in STOREY_HEIGHT_TYPES and not rec.wall_id:
                fill('h', storey.get('clear_height'))
            if storey and code == 'dalle':
                fill('h', storey.get('slab_thickness'))
            for key, (src_type, src_dim) in PROFILE_SECTIONS.get(code, {}).items():
                fill(key, (sections.get(src_type) or {}).get(src_dim))

            vals = {}
            if reinforcements.get(code) and not rec.reinforcement:
                vals['reinforcement'] = reinforcements[code]
            if filled:
                vals['dimensions'] = dims
                vals['issue'] = rec._issue_after_profile(filled, source)
            if vals:
                rec.write(vals)
                completed |= rec

        completed._compute_quantities(apply_defaults=False)
        return completed

    def _issue_after_profile(self, filled, source):
        """Retire les anomalies que les cotes complétées lèvent, et trace
        l'origine de ces cotes."""
        self.ensure_one()
        words = [w for key in filled for w in ISSUE_WORDS.get(key, ())]
        parts = [p for p in (self.issue or '').split(' ; ')
                 if p and not any(w in normalize_text(p) for w in words)]
        parts.append(_("Complété par le plan de détail %s : %s") % (
            source, ", ".join("%s=%.2f m" % (k, v) for k, v in sorted(filled.items()))))
        return " ; ".join(parts)
