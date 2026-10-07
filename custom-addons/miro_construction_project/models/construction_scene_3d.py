import json
import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)

# $INSUNITS -> mètres (cf. construction_analysis_footing)
UNIT_TO_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 14: 0.1}

# Valeurs de dessin quand ni le plan ni le profil structurel ne donnent la
# cote : la scène reste lisible, et l'élément est signalé « supposé ».
DEFAULT_STOREY = {'floor': 0.0, 'clear_height': 2.80, 'slab_thickness': 0.20}
DEFAULT_HEIGHTS = {'poteau': 2.80, 'mur': 2.80, 'poutre': 0.40, 'dalle': 0.20,
                   'semelle': 0.30, 'semelle_filante': 0.30, 'longrine': 0.30}
# Arase inférieure des fondations sous le sol fini du rez-de-chaussée (m)
FOUNDATION_BASE = -0.70

LINEAR_TYPES = ('poutre', 'longrine', 'semelle_filante')
FOUNDATION_TYPES = ('semelle', 'semelle_filante', 'longrine')
# Les ouvertures sont dessinées dans leur mur, pas comme éléments isolés.
SKIPPED_TYPES = ('porte', 'fenetre')


class ProjectProject3D(models.Model):
    """Maquette 3D d'un projet, reconstruite à partir de ses ÉLÉMENTS DE
    CONSTRUCTION (et non d'un plan) : c'est ce qui a été validé qui est
    montré, avec son avancement.

    La géométrie vient de chaque élément (zone source sur son plan,
    dimensions), l'altitude de son niveau via le profil structurel du plan
    de détail (sol, sous-face, épaisseur de plancher). Un mur est dessiné
    depuis son objet construction.wall, percé de ses ouvertures."""
    _inherit = 'project.project'

    def action_open_3d_view(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': '/construction/3d/%s' % self.id,
                'target': 'new'}

    # ------------------------------------------------------------------
    # Scène
    # ------------------------------------------------------------------
    def _construction_scene_3d(self):
        """Scène 3D sérialisable : {project, items, levels, legend}. Coordonnées
        en mètres : x, y en plan, z en altitude (sol fini du RDC = 0)."""
        self.ensure_one()
        profile = self._latest_structure_profile()
        elements = self.env['construction.element'].search([
            ('project_id', '=', self.id)])

        items, walls_done = [], self.env['construction.wall']
        for element in elements:
            code = element.element_type_id.code or ''
            if code in SKIPPED_TYPES:
                continue
            try:
                if code == 'mur' and element.wall_id:
                    if element.wall_id in walls_done:
                        continue
                    walls_done |= element.wall_id
                    item = self._wall_item(element, profile)
                elif code == 'dalle':
                    item = self._slab_item(element, profile)
                else:
                    item = self._box_item(element, code, profile)
            except Exception:  # noqa: BLE001 - un élément illisible ne bloque pas la scène
                _logger.exception("Élément %s non représentable en 3D", element.display_name)
                item = None
            if item:
                items.append(item)

        types = self.env['construction.element.type'].search([])
        return {
            'project': self.name,
            'items': items,
            'levels': sorted({i['level'] for i in items if i['level']}),
            'types': {t.code: t.name for t in types},
            'skipped': len(elements) - len(items),
        }

    def _latest_structure_profile(self):
        analysis = self.env['construction.analysis'].search([
            ('project_id', '=', self.id), ('engine', '=', 'details'),
            ('state', '=', 'done')], order='finished_at desc, id desc', limit=1)
        if not analysis:
            return {}
        try:
            return (json.loads(analysis.result_json or '{}') or {}).get('profile') or {}
        except ValueError:
            return {}

    def _storey(self, level, profile):
        """Sol, sous-face et dessus de plancher du niveau, en mètres."""
        storey = None
        if level and profile:
            storey = self.env['construction.analysis']._storey_for_level(profile, level)
        floor = (storey or {}).get('floor', level.elevation if level else 0.0) or 0.0
        clear = (storey or {}).get('clear_height') or DEFAULT_STOREY['clear_height']
        slab = (storey or {}).get('slab_thickness') or DEFAULT_STOREY['slab_thickness']
        return {'floor': floor, 'ceiling': floor + clear, 'slab_top': floor + clear + slab,
                'known': bool(storey)}

    @staticmethod
    def _unit_scale(element):
        meta = element.source_file_id.metadata_id[:1]
        return UNIT_TO_M.get(meta.units_code, 1.0) if meta else 1.0

    def _base_item(self, element, code, shape, assumed):
        dims = element.dimensions or {}
        info = {
            _("Type"): element.element_type_id.name or code,
            _("Niveau"): element.level_id.name or "—",
            _("Dimensions"): " × ".join(
                "%s %.2f m" % (k, v) for k, v in (
                    ("L", element.dim_l), ("l", element.dim_w), ("h", element.dim_h)) if v),
            _("Béton"): "%.2f m³" % element.qty_beton_m3 if element.qty_beton_m3 else "",
            _("Surface"): "%.2f m²" % element.qty_surface_m2 if element.qty_surface_m2 else "",
            _("Coffrage"): "%.2f m²" % element.qty_coffrage_m2 if element.qty_coffrage_m2 else "",
            _("Acier"): "%.0f kg" % element.qty_acier_kg if element.qty_acier_kg else "",
            _("Ferraillage"): element.reinforcement or "",
            _("Trémies"): element.tremie_summary or "",
            _("Ouvertures"): element.opening_summary or "",
            _("Phases"): "%d" % element.task_count,
        }
        if dims.get('ouvertures_m2'):
            info[_("Ouvertures déduites")] = "%.2f m²" % dims['ouvertures_m2']
        return {
            'id': element.id,
            'key': element.key or element.name,
            'type': code,
            'level': element.level_id.name or "",
            'progress': round(element.progress or 0.0, 1),
            'assumed': assumed,
            'info': {k: v for k, v in info.items() if v},
            'shape': shape,
        }

    # ------------------------------------------------------------------
    # Formes
    # ------------------------------------------------------------------
    def _vertical_span(self, element, code, profile):
        """(altitude basse, altitude haute, cote supposée ?) d'un ouvrage."""
        storey = self._storey(element.level_id, profile)
        h = element.dim_h or DEFAULT_HEIGHTS.get(code, 0.30)
        assumed = not element.dim_h or not storey['known']
        if code in FOUNDATION_TYPES:
            ground = self._storey(self._ground_level(), profile)
            if code == 'longrine':
                # Sous le dallage du rez-de-chaussée
                top = ground['floor'] - ((profile.get('ground_slab') or {}).get('thickness') or 0.12)
                return top - h, top, assumed
            base = ground['floor'] + FOUNDATION_BASE
            return base, base + h, assumed
        if code == 'poutre':
            # Retombée sous le dessus du plancher qu'elle porte
            return storey['slab_top'] - h, storey['slab_top'], assumed
        return storey['floor'], storey['floor'] + h, assumed

    def _ground_level(self):
        levels = self.env['construction.plan.level'].search([], order='sequence, id')
        return levels.filtered(lambda l: (l.code or '').strip().upper() == 'RDC')[:1]

    def _box_item(self, element, code, profile):
        """Poteau, semelle (contour = zone source) ; poutre, longrine,
        semelle filante (zone source = axe, épaissi de leur largeur)."""
        bbox = element.source_bbox or []
        if len(bbox) != 4:
            return None
        s = self._unit_scale(element)
        minx, miny, maxx, maxy = (v * s for v in bbox)
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        dx, dy = maxx - minx, maxy - miny
        if code in LINEAR_TYPES:
            width = element.dim_w or 0.20
            if dx >= dy:
                dx, dy = max(dx, element.dim_l or dx), width
            else:
                dx, dy = width, max(dy, element.dim_l or dy)
        if dx <= 0 or dy <= 0:
            return None
        z0, z1, assumed = self._vertical_span(element, code, profile)
        shape = {'kind': 'box', 'cx': cx, 'cy': cy, 'lx': dx, 'ly': dy, 'z0': z0, 'z1': z1}
        return self._base_item(element, code, shape, assumed)

    def _slab_item(self, element, profile):
        """Dalle : contour extrudé de son épaisseur, percé de ses trémies, posé
        sur la sous-face du plancher de son niveau."""
        bbox = element.source_bbox or []
        if len(bbox) != 4:
            return None
        s = self._unit_scale(element)
        minx, miny, maxx, maxy = (v * s for v in bbox)
        storey = self._storey(element.level_id, profile)
        h = element.dim_h or storey['slab_top'] - storey['ceiling']
        holes = []
        for t in (element.dimensions or {}).get('tremies') or []:
            if len(t.get('bbox') or []) == 4:
                hx0, hy0, hx1, hy1 = (v * s for v in t['bbox'])
                holes.append([[hx0, hy0], [hx1, hy0], [hx1, hy1], [hx0, hy1]])
        shape = {'kind': 'slab',
                 'outline': [[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy]],
                 'holes': holes, 'z0': storey['ceiling'], 'z1': storey['ceiling'] + h}
        return self._base_item(element, 'dalle', shape,
                               not element.dim_h or not storey['known'])

    def _wall_item(self, element, profile):
        """Mur : depuis son objet construction.wall (axe, épaisseur, hauteur),
        percé de ses ouvertures à leur place (allège, hauteur)."""
        wall = element.wall_id
        dx, dy = wall.end_x - wall.start_x, wall.end_y - wall.start_y
        axis = (dx * dx + dy * dy) ** 0.5
        if not axis:
            return None
        f = (wall.length / axis) if wall.length else self._unit_scale(element)
        storey = self._storey(wall.level_id or element.level_id, profile)
        height = wall.height or element.dim_h or storey['ceiling'] - storey['floor']
        openings = wall._opening_layout()
        shape = {'kind': 'wall',
                 'x1': wall.start_x * f, 'y1': wall.start_y * f,
                 'x2': wall.end_x * f, 'y2': wall.end_y * f,
                 'thickness': wall.thickness or element.dim_w or 0.20,
                 'z0': storey['floor'], 'z1': storey['floor'] + height,
                 'openings': openings}
        return self._base_item(element, 'mur', shape,
                               not wall.height or not storey['known'])

    @api.model
    def _scene_json(self, scene):
        """JSON sûr à placer dans une balise <script>."""
        return json.dumps(scene, ensure_ascii=False).replace("</", "<\\/")
