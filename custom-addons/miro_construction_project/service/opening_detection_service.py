# -*- coding: utf-8 -*-
"""
opening_detection_service.py
============================

Détection des ouvertures (portes, fenêtres, baies) dans un DXF, puis
consolidation progressive des ouvertures d'un même niveau au fil des plans
importés — exactement comme les murs (cf. wall_detection_service).

Chaque vue ne montre qu'une partie d'une ouverture : on n'extrait que ce que
la vue permet réellement de voir, et on laisse VIDE le reste.

    Vue en plan  -> position, largeur (longueur prise dans le mur), épaisseur
                    du mur traversé, nature quand le battant est dessiné,
                    côté de façade et position le long de cette façade
                    (hauteur et allège non visibles : laissées vides)
    Vue façade   -> largeur, hauteur, allège, linteau, nature, repère, étage
                    (épaisseur et position en plan non visibles : vides)

Un import ultérieur sur le MÊME niveau complète les champs restés vides des
ouvertures déjà connues, sans jamais écraser une valeur déjà renseignée
(cf. `merge_detected_openings`).

Rapprocher une ouverture vue en plan de la même vue en façade
-------------------------------------------------------------
Les deux dessins n'ont aucun repère commun : la façade est dessinée à part,
à une autre position du DXF. Ce qui est commun, c'est la position de
l'ouverture LE LONG de sa façade, mesurée depuis le bord GAUCHE de la façade
vue de l'extérieur (`facade_offset`). Vue en plan (nord en haut) :

    façade sud    : regardée depuis le sud,   gauche = ouest -> x - x_min
    façade nord   : regardée depuis le nord,  gauche = est   -> x_max - x
    façade est    : regardée depuis l'est,    gauche = sud   -> y - y_min
    façade ouest  : regardée depuis l'ouest,  gauche = nord  -> y_max - y

Vue en façade, c'est simplement l'abscisse depuis le bord gauche du contour.
Deux ouvertures d'un même niveau, d'une même orientation, à la même position
le long de la façade et de même largeur sont la même ouverture.

Comment les ouvertures sont dessinées en plan
---------------------------------------------
    fenêtre / baie : rectangle fermé logé dans l'épaisseur du mur
                     (long côté = largeur, petit côté = épaisseur du mur)
    porte          : arc de débattement centré sur la paumelle + trait du
                     vantail ouvert ; le rayon est la largeur du vantail,
                     l'extrémité de l'arc opposée au vantail donne la
                     direction du mur. Deux arcs dos à dos = porte double.

Calques lus (convention du projet en premier) :

    A-OUV-FEN   fenêtres et baies            -> nature « fenêtre »
    A-OUV-PRT   portes                       -> nature « porte »
    A-OUV-SYMB  symboles : arc de débattement, trait du vantail -> sert
                à reconnaître une porte et son sens ; jamais une baie à lui seul

Les autres calques typés (A-FEN, A-PORTE...) sont aussi acceptés ; un calque
générique (OUVERTURES) ne donne pas la nature : un rectangle y reste
« inconnu » jusqu'à ce qu'une façade la précise.

Dépendances :
    pip install ezdxf shapely
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

try:
    from .plan_analysis import (
        VIEW_ELEVATION, VIEW_PLAN, DxfPlanReader, Outline, PlanContext,
        normalize_text,
    )
    from .facade_detection_service import (
        GENERIC_OPENING_LAYERS, MAX_OPENING_WIDTH, MIN_OPENING_WIDTH,
        OPENING_LABEL_PATTERN, OPENING_LAYERS, FacadeDetectionService,
    )
except ImportError:  # exécution directe du module en ligne de commande
    from plan_analysis import (  # type: ignore[no-redef]
        VIEW_ELEVATION, VIEW_PLAN, DxfPlanReader, Outline, PlanContext,
        normalize_text,
    )
    from facade_detection_service import (  # type: ignore[no-redef]
        GENERIC_OPENING_LAYERS, MAX_OPENING_WIDTH, MIN_OPENING_WIDTH,
        OPENING_LABEL_PATTERN, OPENING_LAYERS, FacadeDetectionService,
    )

logger = logging.getLogger("opening_detection_service")


# ============================================================
# CONFIGURATION
# ============================================================

# Vues dont on sait tirer des ouvertures. Une coupe ne montre qu'une
# ouverture coupée, sans pouvoir dire laquelle : elle n'apporte rien ici.
SUPPORTED_VIEWS = (VIEW_PLAN, VIEW_ELEVATION)

# Calques des murs : ils donnent l'emprise du bâtiment (côté de façade) et
# l'épaisseur du mur traversé par une porte. Les deux conventions de nommage
# rencontrées sont acceptées.
WALL_LAYERS = ("A-MUR-EXT", "A-MUR-INT", "MURS_EXT", "MURS_INT")

# Calques des symboles d'ouverture (arc de débattement, trait du vantail).
# Ils ne portent pas l'ouverture elle-même, seulement son fonctionnement :
# un arc y désigne une porte, mais un rectangle n'y est jamais une baie
# (c'est le dessin du vitrage ou du dormant, déjà tracé sur A-OUV-FEN).
SYMBOL_LAYERS = ("A-OUV-SYMB",)

# Épaisseur plausible d'un mur, donc de la feuillure d'une ouverture (m)
MIN_OPENING_DEPTH = 0.05
MAX_OPENING_DEPTH = 0.80

# Vantail de porte plausible (rayon de l'arc de débattement, m)
MIN_LEAF_WIDTH = 0.50
MAX_LEAF_WIDTH = 1.60
# Un débattement de porte fait un quart de tour, à la tolérance du dessin
MIN_SWING_ANGLE = 60.0
MAX_SWING_ANGLE = 120.0

# Tolérances géométriques (m)
LEAF_TOLERANCE = 0.05             # trait du vantail : part de la paumelle
DOUBLE_DOOR_TOLERANCE = 0.10      # deux vantaux qui se rejoignent
HOST_WALL_MAX_DISTANCE = 0.60     # axe de la porte -> axe du mur
DEDUP_TOLERANCE = 0.10            # même ouverture dessinée deux fois
EXTERIOR_TOLERANCE = 0.15         # au-delà de l'épaisseur du mur
MIN_ENVELOPE_SIZE = 2.00          # contour de bâtiment plausible
ENVELOPE_PAD = 0.50               # une ouverture déborde du nu extérieur
ENVELOPE_JOIN = 0.05              # soude les morceaux de murs qui se touchent
LABEL_MAX_DISTANCE = 1.00         # repère « F1 » -> ouverture

# Rapprochement de deux observations de la même ouverture (m)
SAME_POSITION_TOLERANCE = 0.30    # deux vues en plan : centres
SAME_OFFSET_TOLERANCE = 0.30      # plan <-> façade : position le long de la façade
SAME_WIDTH_TOLERANCE = 0.20       # largeurs compatibles

TYPE_LABELS = {
    "window": "Fenêtre",
    "french_window": "Porte-fenêtre",
    "door": "Porte",
    "garage_door": "Porte de garage",
    "bay": "Baie",
    "vent": "Ouverture technique",
    "unknown": "Ouverture",
}

ORIENTATIONS = ("nord", "sud", "est", "ouest")


# ============================================================
# STRUCTURE DE DONNÉES — MIROIR DU MODÈLE ODOO construction.opening
# ============================================================

EMPTY_SELECTION_VALUES = ("unknown", "", None, False)
SELECTION_FIELDS = ("opening_type", "wall_position")
FLOAT_FIELDS = ("width", "thickness", "height", "sill_height",
                "lintel_height", "facade_offset", "confidence")
GEOMETRY_FIELDS = ("start_x", "start_y", "end_x", "end_y", "center_x", "center_y")


@dataclass
class DetectedOpening:
    """Ouverture telle que vue par UNE vue. Tout champ que la vue ne permet
    pas d'observer vaut None et reste vide côté Odoo, en attendant un plan
    d'une autre vue qui le renseignera."""

    name: str
    match_key: str = ""
    source_view: str = VIEW_PLAN
    level: Optional[str] = None
    opening_type: str = "unknown"
    wall_position: str = "unknown"        # exterior / interior
    orientation: Optional[str] = None
    facade_offset: Optional[float] = None  # centre, depuis le bord gauche de la façade
    mark: Optional[str] = None
    layer: Optional[str] = None
    # Position en plan : l'axe de l'ouverture dans le mur
    start_x: Optional[float] = None
    start_y: Optional[float] = None
    end_x: Optional[float] = None
    end_y: Optional[float] = None
    center_x: Optional[float] = None
    center_y: Optional[float] = None
    # Dimensions (m)
    width: Optional[float] = None          # longueur prise dans le mur
    thickness: Optional[float] = None      # épaisseur du mur traversé
    height: Optional[float] = None
    sill_height: Optional[float] = None    # allège, au-dessus du sol du niveau
    lintel_height: Optional[float] = None  # hauteur sous linteau, idem
    confidence: float = 0.0
    detection_method: str = "layer"

    # Étage détecté sur une façade multi-niveaux (0 = le plus bas), résolu
    # vers un construction.plan.level par l'appelant, comme pour les murs.
    floor_index: Optional[int] = None

    ODOO_FIELDS = (
        "name", "match_key", "opening_type", "wall_position", "orientation",
        "facade_offset", "mark", "layer", "start_x", "start_y", "end_x",
        "end_y", "center_x", "center_y", "width", "thickness", "height",
        "sill_height", "lintel_height", "confidence", "detection_method",
    )

    def to_odoo_dict(self) -> dict:
        return asdict(self)

    def to_odoo_vals(self) -> dict:
        """Valeurs à écrire dans construction.opening : les champs non
        observés (None) sont omis pour rester vides en base."""
        vals = {}
        for name in self.ODOO_FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            # ezdxf rend des flottants numpy : on les ramène au type Python.
            vals[name] = round(float(value), 3) if isinstance(value, float) else value
        return vals

    @property
    def has_axis(self) -> bool:
        return None not in (self.start_x, self.start_y, self.end_x, self.end_y)

    @property
    def axis(self) -> Optional[LineString]:
        if not self.has_axis:
            return None
        return LineString([(self.start_x, self.start_y), (self.end_x, self.end_y)])


# ============================================================
# SERVICE PRINCIPAL
# ============================================================

@dataclass
class _HostWall:
    """Mur vu en plan (paire de faces parallèles), en mètres."""

    axis: LineString
    thickness: float
    layer: str


class OpeningDetectionService(DxfPlanReader):
    """Lit un DXF et en extrait les ouvertures, selon ce que la vue permet de
    voir. Toutes les longueurs renvoyées sont en mètres : `unit_scale` donne
    le nombre de mètres par unité de dessin, relevé à l'import ($INSUNITS)."""

    def __init__(self, dxf_path: str, context: Optional[PlanContext] = None,
                 unit_scale: float = 1.0):
        super().__init__(dxf_path)
        self.context = context or PlanContext()
        self.unit_scale = unit_scale or 1.0
        self._layer_index = self._build_layer_index()

    # --------------------------------------------------------
    # POINT D'ENTRÉE — aiguillage selon le type de vue
    # --------------------------------------------------------

    def detect_openings(self) -> List[DetectedOpening]:
        ctx = self.context
        logger.info("Détection des ouvertures sur %s (vue=%s, niveau=%s)",
                    self.dxf_path, ctx.view, ctx.level_label or "-")

        if ctx.view not in SUPPORTED_VIEWS:
            logger.info("La vue « %s » ne permet pas d'extraire d'ouvertures",
                        ctx.view)
            return []

        if ctx.view == VIEW_PLAN:
            openings = self._detect_from_plan_view()
        else:
            openings = self._detect_from_elevation_view()

        for opening in openings:
            if opening.floor_index is None:
                opening.level = ctx.level
            opening.source_view = ctx.view
        self._make_keys_unique(openings)

        logger.info("Détection terminée : %d ouverture(s) (vue %s)",
                    len(openings), ctx.view)
        return openings

    @staticmethod
    def _make_keys_unique(openings: List[DetectedOpening]) -> None:
        """Deux ouvertures d'un même étage ne partagent jamais une clé : le
        brouillon, puis l'élément, en dépendent. Un doublon (même façade, même
        position à l'arrondi près) reçoit un suffixe."""
        seen: Dict[Tuple[Optional[int], str], int] = {}
        for opening in openings:
            ident = (opening.floor_index, opening.match_key)
            count = seen.get(ident, 0)
            seen[ident] = count + 1
            if count:
                opening.match_key = "%s-%d" % (opening.match_key, count + 1)

    # --------------------------------------------------------
    # CALQUES : correspondance tolérante
    # --------------------------------------------------------

    def _build_layer_index(self) -> Dict[str, str]:
        """Calques présents, indexés par leur nom normalisé : la casse et les
        accents varient d'un bureau d'études à l'autre."""
        index: Dict[str, str] = {}
        try:
            for layer in self.doc.layers:
                index[normalize_text(layer.dxf.name)] = layer.dxf.name
        except Exception as exc:
            logger.debug("Lecture de la table des calques impossible : %s", exc)
        return index

    def _layers(self, wanted: Sequence[str]) -> List[str]:
        found = []
        for name in wanted:
            real = self._layer_index.get(normalize_text(name))
            if real and real not in found:
                found.append(real)
        return found

    def _opening_layer_types(self) -> Dict[str, str]:
        """{calque réel: nature} ; « unknown » pour un calque générique."""
        types: Dict[str, str] = {}
        for opening_type, names in OPENING_LAYERS.items():
            for layer in self._layers(names):
                types[layer] = opening_type
        for layer in self._layers(GENERIC_OPENING_LAYERS):
            types.setdefault(layer, "unknown")
        return types

    # --------------------------------------------------------
    # MISE À L'ÉCHELLE : tout est converti en mètres à la lecture
    # --------------------------------------------------------

    def _m(self, value: float) -> float:
        return value * self.unit_scale

    def _point(self, x: float, y: float) -> Tuple[float, float]:
        return self._m(x), self._m(y)

    def _segments_m(self, layers: Sequence[str]) -> List[Tuple[LineString, str]]:
        return [
            (LineString([self._point(*c) for c in line.coords]), layer)
            for line, layer in self.collect_segments(layers, include_blocks=True)
        ]

    def _outlines_m(self, layers: Sequence[str]) -> List[Outline]:
        scaled = []
        for outline in self.collect_closed_outlines(layers, include_blocks=True):
            points = [self._point(x, y) for x, y in outline.points]
            box = self.bounding_box(points)
            if box:
                scaled.append(Outline(*box, layer=outline.layer, points=points))
        return scaled

    # ========================================================
    # VUE EN PLAN — position, largeur, épaisseur
    # (hauteur et allège non observables : laissées vides)
    # ========================================================

    def _detect_from_plan_view(self) -> List[DetectedOpening]:
        layer_types = self._opening_layer_types()
        if not layer_types and not self._layers(SYMBOL_LAYERS):
            logger.warning("Aucun calque d'ouvertures dans %s (attendus : %s)",
                           self.dxf_path, ", ".join(
                               [n for names in OPENING_LAYERS.values() for n in names]
                               + list(GENERIC_OPENING_LAYERS) + list(SYMBOL_LAYERS)))
            return []

        host_walls = self._collect_host_walls()
        opening_layers = list(layer_types)
        symbol_layers = self._layers(SYMBOL_LAYERS)

        windows = self._detect_plan_windows(opening_layers, layer_types)
        doors = self._detect_plan_doors(opening_layers + symbol_layers,
                                        layer_types, host_walls)
        logger.info("Candidats : %d rectangle(s), %d battant(s) de porte",
                    len(windows), len(doors))

        doors = self._merge_double_doors(doors)
        openings = self._merge_doors_with_frames(doors, windows)
        openings = self._deduplicate(openings)

        for opening in openings:
            self._fill_thickness_from_wall(opening, host_walls)
        envelopes = self._collect_envelopes(openings)
        for opening in openings:
            self._classify_side(opening, envelopes)
        self._attach_marks(openings)
        self._name_and_key_plan_openings(openings)
        return openings

    # --------------------------------------------------------
    # MURS ET EMPRISE DU BÂTIMENT
    # --------------------------------------------------------

    def _collect_host_walls(self) -> List[_HostWall]:
        """Murs vus en plan : deux faces parallèles écartées d'une épaisseur
        plausible (même règle que la détection de murs)."""
        segments = self._segments_m(self._layers(WALL_LAYERS))
        if not segments:
            return []
        return [
            _HostWall(axis=pair.axis, thickness=pair.width, layer=pair.layer_a)
            for pair in self.find_parallel_pairs(
                segments, min_width=MIN_OPENING_DEPTH,
                max_width=MAX_OPENING_DEPTH, min_length=0.30)
        ]

    def _collect_envelopes(self, openings: List[DetectedOpening]
                           ) -> List[Tuple[float, float, float, float]]:
        """Emprise extérieure de chaque bâtiment du dessin.

        On ne se fie pas au nom des calques (« extérieur » / « intérieur ») :
        beaucoup de plans tracent tous les murs sur le même calque. On soude
        plutôt toute la géométrie des murs ET des ouvertures, qui referment
        les baies : chaque bloc d'un seul tenant est un bâtiment, et sa boîte
        englobante est son nu extérieur. Un DXF qui porte le RDC et l'étage
        côte à côte donne ainsi deux emprises distinctes."""
        shapes = [line.buffer(ENVELOPE_JOIN)
                  for line, _layer in self._segments_m(self._layers(WALL_LAYERS))]
        shapes += [o.axis.buffer(ENVELOPE_JOIN + (o.thickness or 0.0) / 2.0)
                   for o in openings]
        if not shapes:
            return []
        try:
            union = unary_union(shapes)
        except Exception as exc:
            logger.warning("Emprise du bâtiment incalculable : %s", exc)
            return []

        boxes = []
        for part in getattr(union, "geoms", [union]):
            minx, miny, maxx, maxy = part.bounds
            box = (minx + ENVELOPE_JOIN, miny + ENVELOPE_JOIN,
                   maxx - ENVELOPE_JOIN, maxy - ENVELOPE_JOIN)
            if (box[2] - box[0] >= MIN_ENVELOPE_SIZE
                    and box[3] - box[1] >= MIN_ENVELOPE_SIZE):
                boxes.append(box)
        return boxes

    @staticmethod
    def _box_inside(inner, outer, pad: float = 0.0) -> bool:
        return (outer[0] - pad <= inner[0] and inner[2] <= outer[2] + pad
                and outer[1] - pad <= inner[1] and inner[3] <= outer[3] + pad)

    # --------------------------------------------------------
    # FENÊTRES : rectangle logé dans l'épaisseur du mur
    # --------------------------------------------------------

    def _detect_plan_windows(self, layers: List[str],
                             layer_types: Dict[str, str]) -> List[DetectedOpening]:
        found: List[DetectedOpening] = []
        for outline in self._outlines_m(layers):
            rect = self._rectangle_axis(outline.points)
            if not rect:
                continue
            axis, width, depth = rect
            if not (MIN_OPENING_WIDTH <= width <= MAX_OPENING_WIDTH
                    and MIN_OPENING_DEPTH <= depth <= MAX_OPENING_DEPTH):
                # Trop profond pour un mur : c'est une ouverture dessinée en
                # élévation, pas en plan (DXF qui mêle les deux vues).
                continue
            found.append(self._plan_opening(
                axis, width, thickness=depth,
                opening_type=layer_types.get(outline.layer, "unknown"),
                layer=outline.layer, confidence=80.0))
        return found

    @staticmethod
    def _rectangle_axis(points) -> Optional[Tuple[LineString, float, float]]:
        """(axe médian le long du grand côté, longueur, profondeur) du plus
        petit rectangle englobant — couvre aussi un mur oblique."""
        try:
            polygon = Polygon(points)
            if polygon.area <= 0:
                return None
            rect = polygon.minimum_rotated_rectangle
            corners = list(rect.exterior.coords)[:4]
        except Exception:
            return None
        if len(corners) < 4:
            return None
        a, b, c, d = corners
        side_ab = math.dist(a, b)
        side_bc = math.dist(b, c)
        if side_ab >= side_bc:
            start = ((a[0] + d[0]) / 2.0, (a[1] + d[1]) / 2.0)
            end = ((b[0] + c[0]) / 2.0, (b[1] + c[1]) / 2.0)
            return LineString([start, end]), side_ab, side_bc
        start = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        end = ((d[0] + c[0]) / 2.0, (d[1] + c[1]) / 2.0)
        return LineString([start, end]), side_bc, side_ab

    # --------------------------------------------------------
    # PORTES : arc de débattement + vantail
    # --------------------------------------------------------

    def _detect_plan_doors(self, layers: List[str], layer_types: Dict[str, str],
                           host_walls: List[_HostWall]) -> List[DetectedOpening]:
        wanted = set(layers)
        arcs, leaves = [], []
        entities = [(e, e.dxf.get("layer", "0")) for e in self.msp.query("ARC LINE")]
        entities += [(e, l) for e, l in self.block_entities()
                     if e.dxftype() in ("ARC", "LINE")]
        for entity, layer in entities:
            if layer not in wanted:
                continue
            if entity.dxftype() == "ARC":
                arcs.append((entity, layer))
            else:
                start = self._point(entity.dxf.start.x, entity.dxf.start.y)
                end = self._point(entity.dxf.end.x, entity.dxf.end.y)
                if start != end:
                    leaves.append((start, end))

        doors: List[DetectedOpening] = []
        for arc, layer in arcs:
            door = self._door_from_arc(arc, layer, layer_types, leaves, host_walls)
            if door:
                doors.append(door)
        return doors

    def _door_from_arc(self, arc, layer, layer_types, leaves,
                       host_walls) -> Optional[DetectedOpening]:
        radius = self._m(arc.dxf.radius)
        sweep = (arc.dxf.end_angle - arc.dxf.start_angle) % 360.0
        if not (MIN_LEAF_WIDTH <= radius <= MAX_LEAF_WIDTH
                and MIN_SWING_ANGLE <= sweep <= MAX_SWING_ANGLE):
            return None

        hinge = self._point(arc.dxf.center.x, arc.dxf.center.y)
        ends = [math.radians(arc.dxf.start_angle), math.radians(arc.dxf.end_angle)]
        directions = [(math.cos(a), math.sin(a)) for a in ends]

        # L'une des extrémités de l'arc est la position fermée, dans le mur :
        # c'est celle qui prolonge un mur voisin. Le trait du vantail ne
        # suffit pas — selon le dessinateur, il est tracé ouvert ou fermé.
        closed_index = self._closed_index_from_walls(hinge, radius, directions,
                                                     host_walls)
        confidence = 85.0
        if closed_index is None:
            # Pas de mur lisible : le vantail est supposé dessiné ouvert.
            open_index = self._leaf_direction_index(hinge, radius, directions, leaves)
            closed_index = 0 if open_index is None else 1 - open_index
            confidence = 75.0 if open_index is not None else 60.0
        closed = directions[closed_index]

        tip = (hinge[0] + closed[0] * radius, hinge[1] + closed[1] * radius)
        opening_type = layer_types.get(layer, "unknown")
        if opening_type in ("unknown", "window", "bay"):
            # Un battant dessiné est la signature d'une porte (ou d'une
            # porte-fenêtre, qu'une façade précisera).
            opening_type = "door"
        return self._plan_opening(
            LineString([hinge, tip]), radius, thickness=None,
            opening_type=opening_type, layer=layer, confidence=confidence)

    @staticmethod
    def _leaf_direction_index(hinge, radius, directions, leaves) -> Optional[int]:
        for start, end in leaves:
            for origin, far in ((start, end), (end, start)):
                if math.dist(origin, hinge) > LEAF_TOLERANCE:
                    continue
                if abs(math.dist(origin, far) - radius) > max(radius * 0.10, LEAF_TOLERANCE):
                    continue
                for index, (dx, dy) in enumerate(directions):
                    tip = (hinge[0] + dx * radius, hinge[1] + dy * radius)
                    if math.dist(tip, far) <= max(radius * 0.10, LEAF_TOLERANCE):
                        return index
        return None

    def _closed_index_from_walls(self, hinge, radius, directions,
                                 host_walls) -> Optional[int]:
        """Extrémité de l'arc dont le vantail fermé prolonge un mur : même
        direction que le mur, et axe à moins de HOST_WALL_MAX_DISTANCE du
        sien (les deux morceaux de mur s'arrêtent au bord de la baie)."""
        best_index, best_distance = None, HOST_WALL_MAX_DISTANCE
        for index, (dx, dy) in enumerate(directions):
            leaf = LineString([hinge, (hinge[0] + dx * radius, hinge[1] + dy * radius)])
            for wall in host_walls:
                if not self._parallel(leaf, wall.axis):
                    continue
                distance = wall.axis.distance(leaf)
                if distance < best_distance:
                    best_index, best_distance = index, distance
        return best_index

    def _merge_double_doors(self, doors: List[DetectedOpening]) -> List[DetectedOpening]:
        """Deux vantaux sur le même axe dont les extrémités libres se
        rejoignent forment une seule porte double."""
        merged, used = [], set()
        for i, a in enumerate(doors):
            if i in used:
                continue
            partner = None
            for j in range(i + 1, len(doors)):
                b = doors[j]
                if j in used:
                    continue
                if (math.dist((a.end_x, a.end_y), (b.end_x, b.end_y)) <= DOUBLE_DOOR_TOLERANCE
                        and self._parallel(a.axis, b.axis)):
                    partner = j
                    break
            if partner is None:
                merged.append(a)
                continue
            used.add(partner)
            b = doors[partner]
            merged.append(self._plan_opening(
                LineString([(a.start_x, a.start_y), (b.start_x, b.start_y)]),
                a.width + b.width, thickness=None, opening_type=a.opening_type,
                layer=a.layer, confidence=min(a.confidence, b.confidence) + 2.0))
        return merged

    def _merge_doors_with_frames(self, doors, windows) -> List[DetectedOpening]:
        """Une porte est souvent dessinée AVEC son dormant (rectangle dans le
        mur) : on garde la porte, et l'épaisseur que donne le rectangle."""
        remaining = list(windows)
        for door in doors:
            for window in remaining[:]:
                if (math.dist((door.center_x, door.center_y),
                              (window.center_x, window.center_y)) <= window.width / 2.0
                        and abs(door.width - window.width) <= SAME_WIDTH_TOLERANCE
                        and self._parallel(door.axis, window.axis)):
                    door.thickness = door.thickness or window.thickness
                    door.confidence = min(door.confidence + 5.0, 95.0)
                    remaining.remove(window)
                    break
        return doors + remaining

    @staticmethod
    def _parallel(a: LineString, b: LineString, tolerance: float = 5.0) -> bool:
        angle_a = DxfPlanReader.line_angle(a)
        angle_b = DxfPlanReader.line_angle(b)
        diff = abs(angle_a - angle_b) % 180.0
        return min(diff, 180.0 - diff) <= tolerance

    @staticmethod
    def _deduplicate(openings: List[DetectedOpening]) -> List[DetectedOpening]:
        kept: List[DetectedOpening] = []
        for opening in sorted(openings, key=lambda o: -o.confidence):
            if not any(
                    math.dist((opening.center_x, opening.center_y),
                              (other.center_x, other.center_y)) < DEDUP_TOLERANCE
                    and abs(opening.width - other.width) < DEDUP_TOLERANCE
                    for other in kept):
                kept.append(opening)
        return kept

    # --------------------------------------------------------
    # ÉPAISSEUR, CÔTÉ DE FAÇADE, REPÈRE
    # --------------------------------------------------------

    def _fill_thickness_from_wall(self, opening: DetectedOpening,
                                  host_walls: List[_HostWall]) -> None:
        """Une porte n'a pas d'épaisseur propre : c'est celle du mur qu'elle
        traverse. On cherche le mur parallèle dont l'axe passe au plus près.
        Les deux morceaux de mur de part et d'autre de la baie s'arrêtent à
        son bord : leur axe est dans le prolongement de l'ouverture."""
        best, best_distance = None, HOST_WALL_MAX_DISTANCE
        axis = opening.axis
        for wall in host_walls:
            if not self._parallel(axis, wall.axis):
                continue
            distance = wall.axis.distance(axis)
            if distance < best_distance:
                best, best_distance = wall, distance
        if not best:
            return
        if not opening.thickness:
            # Porte : la paumelle est sur le nu du mur, pas sur son axe. On
            # recale l'ouverture sur l'axe du mur pour qu'une autre vue en
            # plan du même niveau la retrouve au même endroit.
            opening.thickness = best.thickness
            self._move_onto(opening, best.axis)
        opening.confidence = min(opening.confidence + 5.0, 95.0)

    @staticmethod
    def _move_onto(opening: DetectedOpening, axis: LineString) -> None:
        (x1, y1), (x2, y2) = axis.coords[0], axis.coords[-1]
        length = math.hypot(x2 - x1, y2 - y1)
        if not length:
            return
        ux, uy = (x2 - x1) / length, (y2 - y1) / length

        def project(x, y):
            t = (x - x1) * ux + (y - y1) * uy
            return x1 + ux * t, y1 + uy * t

        opening.start_x, opening.start_y = project(opening.start_x, opening.start_y)
        opening.end_x, opening.end_y = project(opening.end_x, opening.end_y)
        opening.center_x = (opening.start_x + opening.end_x) / 2.0
        opening.center_y = (opening.start_y + opening.end_y) / 2.0

    def _classify_side(self, opening: DetectedOpening, envelopes) -> None:
        """Extérieure si l'ouverture est dans l'épaisseur du mur périphérique ;
        le bord d'emprise le plus proche donne son orientation et sa position
        le long de la façade, vue de l'extérieur (cf. en-tête du module)."""
        cx, cy = opening.center_x, opening.center_y
        envelope = next((box for box in envelopes
                         if self._box_inside((cx, cy, cx, cy), box, ENVELOPE_PAD)), None)
        if not envelope:
            return
        minx, miny, maxx, maxy = envelope
        horizontal = self._is_horizontal(opening.axis)
        candidates = (
            [("sud", cy - miny, cx - minx), ("nord", maxy - cy, maxx - cx)]
            if horizontal else
            [("ouest", cx - minx, maxy - cy), ("est", maxx - cx, cy - miny)]
        )
        side, distance, offset = min(candidates, key=lambda c: abs(c[1]))
        limit = (opening.thickness or MAX_OPENING_DEPTH / 2.0) + EXTERIOR_TOLERANCE
        if abs(distance) <= limit:
            opening.wall_position = "exterior"
            opening.orientation = side
            opening.facade_offset = offset
        else:
            opening.wall_position = "interior"

    @staticmethod
    def _is_horizontal(axis: LineString) -> bool:
        angle = DxfPlanReader.line_angle(axis)
        return angle < 45 or angle > 135

    def _attach_marks(self, openings: List[DetectedOpening]) -> None:
        marks = [
            (text.strip().upper(), *self._point(x, y))
            for text, x, y in self.collect_texts_with_position()
            if OPENING_LABEL_PATTERN.match(text or "")
        ]
        if not marks:
            return
        for opening in openings:
            best, best_distance = None, LABEL_MAX_DISTANCE
            for text, x, y in marks:
                distance = math.dist((x, y), (opening.center_x, opening.center_y))
                if distance < best_distance:
                    best, best_distance = text, distance
            if best:
                opening.mark = best
                opening.confidence = min(opening.confidence + 5.0, 95.0)

    def _name_and_key_plan_openings(self, openings: List[DetectedOpening]) -> None:
        """Noms lisibles, numérotés le long de chaque façade ; clé d'identité
        portant la position le long de la façade (extérieures) ou dans le
        plan (intérieures)."""
        ctx = self.context
        by_side: Dict[str, List[DetectedOpening]] = {}
        interior: List[DetectedOpening] = []
        for opening in openings:
            if opening.orientation:
                by_side.setdefault(opening.orientation, []).append(opening)
            else:
                interior.append(opening)

        for side, side_openings in by_side.items():
            side_openings.sort(key=lambda o: o.facade_offset)
            for index, opening in enumerate(side_openings, start=1):
                opening.name = "%s façade %s %d" % (
                    TYPE_LABELS.get(opening.opening_type, "Ouverture"), side, index)
                opening.match_key = ctx.match_key(
                    "ouv-%s-%.2f" % (side, opening.facade_offset))

        interior.sort(key=lambda o: (round(o.center_y, 1), o.center_x))
        for index, opening in enumerate(interior, start=1):
            opening.name = "%s intérieure %d" % (
                TYPE_LABELS.get(opening.opening_type, "Ouverture"), index)
            opening.match_key = ctx.match_key(
                "ouv-axe-%.2f-%.2f" % (opening.center_x, opening.center_y))

    @staticmethod
    def _plan_opening(axis: LineString, width: float, thickness: Optional[float],
                      opening_type: str, layer: str,
                      confidence: float) -> DetectedOpening:
        (sx, sy), (ex, ey) = axis.coords[0], axis.coords[-1]
        return DetectedOpening(
            name=TYPE_LABELS.get(opening_type, "Ouverture"),
            opening_type=opening_type,
            layer=layer,
            start_x=sx, start_y=sy, end_x=ex, end_y=ey,
            center_x=(sx + ex) / 2.0, center_y=(sy + ey) / 2.0,
            width=width,
            thickness=thickness,
            # hauteur et allège non observables sur une vue en plan
            height=None, sill_height=None, lintel_height=None,
            confidence=confidence,
            detection_method="layer",
        )

    # ========================================================
    # VUE FAÇADE — largeur, hauteur, allège, linteau, nature
    # (épaisseur et position en plan non observables : laissées vides)
    # ========================================================

    def _detect_from_elevation_view(self) -> List[DetectedOpening]:
        """La lecture d'une façade (contours, orientations, bandes d'étage,
        ouvertures) est celle du service façade : on ne la refait pas, on en
        traduit les ouvertures. Les hauteurs y sont comptées depuis le bas de
        la façade ; ici on les ramène au sol de l'étage, seule cote de pose
        comparable d'un niveau à l'autre."""
        facade_service = FacadeDetectionService(
            self.dxf_path, context=self.context, unit_scale=self.unit_scale)
        openings: List[DetectedOpening] = []

        for index, facade in enumerate(facade_service.detect_facades()):
            floors = {level.floor_index: level for level in facade.levels}
            label = facade.orientation or "sans-orientation-%d" % index
            counters: Dict[Optional[int], int] = {}

            for seen in sorted(facade.openings, key=lambda o: (o.floor_index or 0, o.pos_x)):
                floor = floors.get(seen.floor_index)
                floor_bottom = floor.bottom_elevation if floor else 0.0
                offset = seen.center_x - facade.min_x
                counters[seen.floor_index] = counters.get(seen.floor_index, 0) + 1

                name = "%s façade %s %d" % (
                    TYPE_LABELS.get(seen.opening_type, "Ouverture"), label,
                    counters[seen.floor_index])
                if len(floors) > 1 and seen.floor_index is not None:
                    name += " (étage %d)" % seen.floor_index

                openings.append(DetectedOpening(
                    name=name,
                    # Le niveau est préfixé par l'appelant une fois l'étage
                    # résolu (cf. _resolve_wall_levels côté Odoo).
                    match_key="ouv-%s-%.2f" % (label, offset),
                    opening_type=seen.opening_type,
                    wall_position="exterior",
                    orientation=facade.orientation,
                    facade_offset=offset,
                    mark=seen.mark,
                    layer=seen.layer,
                    width=seen.width,
                    height=seen.height,
                    sill_height=max(seen.sill_height - floor_bottom, 0.0),
                    lintel_height=max(seen.lintel_height - floor_bottom, 0.0),
                    # épaisseur et position en plan non observables en façade
                    thickness=None,
                    confidence=seen.confidence if facade.orientation
                    else min(seen.confidence, 60.0),
                    detection_method="geometry",
                    floor_index=seen.floor_index if len(floors) > 1 else None,
                ))
        return openings

    # --------------------------------------------------------
    # EXPORT
    # --------------------------------------------------------

    def export_json(self, openings: List[DetectedOpening], output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as stream:
            json.dump([o.to_odoo_dict() for o in openings], stream,
                      ensure_ascii=False, indent=2)
        logger.info("Export JSON écrit : %s (%d ouvertures)", output_path, len(openings))


# ============================================================
# CONSOLIDATION : COMPLÉTER LES OUVERTURES DÉJÀ CONNUES
# ============================================================

@dataclass
class OpeningMergePlan:
    """Ce qu'il reste à écrire côté Odoo. `updates` ne contient QUE des
    champs jusque-là vides."""

    creates: List[dict]
    updates: List[Tuple[int, dict]]


def has_axis(opening: dict) -> bool:
    """Ouverture localisée en plan : extrémités connues et distinctes (une
    coordonnée nulle est une position valable)."""
    start = (opening.get("start_x") or 0.0, opening.get("start_y") or 0.0)
    end = (opening.get("end_x") or 0.0, opening.get("end_y") or 0.0)
    return start != end


def is_empty_value(field: str, value) -> bool:
    """Champ jamais observé : un flottant Odoo non renseigné vaut 0.0, une
    sélection non renseignée vaut « unknown »."""
    if value in (None, False, ""):
        return True
    if field in SELECTION_FIELDS:
        return value in EMPTY_SELECTION_VALUES
    if field in FLOAT_FIELDS or field in GEOMETRY_FIELDS:
        return not value
    return False


def _fields_to_fill(existing: dict, detected: DetectedOpening) -> dict:
    """Champs observés par cette vue et encore vides sur l'ouverture connue.
    Le nom et la clé déjà posés ne sont jamais réécrits."""
    detected_vals = detected.to_odoo_vals()
    vals = {}
    for field, value in detected_vals.items():
        if field in ("name", "match_key", "confidence") or field in GEOMETRY_FIELDS:
            continue
        if is_empty_value(field, value):
            continue
        if is_empty_value(field, existing.get(field)):
            vals[field] = value

    # La géométrie se complète en bloc : seule l'absence d'axe signale une
    # ouverture pas encore localisée en plan.
    if detected.has_axis and not has_axis(existing):
        vals.update({f: detected_vals[f] for f in GEOMETRY_FIELDS if f in detected_vals})

    if detected.confidence > (existing.get("confidence") or 0.0):
        vals["confidence"] = round(detected.confidence, 2)

    if vals and existing.get("detection_method") not in (None, "combined"):
        vals["detection_method"] = "combined"

    if not existing.get("match_key"):
        vals["match_key"] = detected.match_key

    # « Ouverture façade sud 1 » devient « Fenêtre façade sud 1 » quand une
    # autre vue en donne la nature. Un nom saisi à la main n'est pas touché.
    generic = TYPE_LABELS["unknown"]
    name = existing.get("name") or ""
    if "opening_type" in vals and name.startswith(generic + " "):
        vals["name"] = TYPE_LABELS.get(vals["opening_type"], generic) + name[len(generic):]
    return vals


def _widths_compatible(existing: dict, detected: DetectedOpening) -> bool:
    if not existing.get("width") or not detected.width:
        return True
    return abs(existing["width"] - detected.width) <= SAME_WIDTH_TOLERANCE


def _match_score(existing: dict, detected: DetectedOpening) -> Optional[float]:
    """Score de rapprochement, ou None si ce n'est pas la même ouverture.

    Du plus sûr au plus faible :
      1. même clé d'identité (même niveau, même désignation)
      2. deux vues en plan : centres superposés
      3. plan <-> façade : même orientation, même position le long de la
         façade, largeurs compatibles"""
    if existing.get("match_key") and existing["match_key"] == detected.match_key:
        return 100.0
    if not _widths_compatible(existing, detected):
        return None

    if detected.has_axis and has_axis(existing):
        distance = math.dist(
            (existing.get("center_x") or 0.0, existing.get("center_y") or 0.0),
            (detected.center_x, detected.center_y))
        if distance > SAME_POSITION_TOLERANCE:
            return None
        return 90.0 - distance

    if (detected.orientation and existing.get("orientation") == detected.orientation
            and detected.facade_offset and existing.get("facade_offset")):
        delta = abs(existing["facade_offset"] - detected.facade_offset)
        if delta > SAME_OFFSET_TOLERANCE:
            return None
        return 80.0 - delta

    return None


def merge_detected_openings(existing_openings: Sequence[dict],
                            detected_openings: Sequence[DetectedOpening]
                            ) -> OpeningMergePlan:
    """Consolide les ouvertures détectées avec celles déjà connues pour le
    même niveau. Règle unique : on ne remplit que le vide.

    Appariement un pour un, du meilleur score au moins bon : deux fenêtres
    voisines de même largeur ne doivent pas se disputer la même ouverture."""
    available = {o["id"]: o for o in existing_openings}
    candidates = []
    for index, detected in enumerate(detected_openings):
        for opening_id, existing in available.items():
            score = _match_score(existing, detected)
            if score is not None:
                candidates.append((score, index, opening_id))

    matched: Dict[int, int] = {}
    taken = set()
    for score, index, opening_id in sorted(candidates, reverse=True):
        if index in matched or opening_id in taken:
            continue
        matched[index] = opening_id
        taken.add(opening_id)

    creates: List[dict] = []
    updates: List[Tuple[int, dict]] = []
    for index, detected in enumerate(detected_openings):
        opening_id = matched.get(index)
        if opening_id is None:
            creates.append(detected.to_odoo_vals())
            continue
        vals = _fields_to_fill(available[opening_id], detected)
        if vals:
            updates.append((opening_id, vals))
    return OpeningMergePlan(creates=creates, updates=updates)


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Détection des ouvertures dans un DXF")
    parser.add_argument("dxf_path", help="Chemin du fichier DXF à analyser")
    parser.add_argument("-o", "--output", default="ouvertures_detectees.json")
    parser.add_argument("-v", "--view", default="plan",
                        help="Type de vue du plan : plan, facade")
    parser.add_argument("-n", "--level", default=None, help="Niveau : R+0, R+1...")
    parser.add_argument("-s", "--scale", type=float, default=1.0,
                        help="Mètres par unité de dessin (0.001 si le DXF est en mm)")
    args = parser.parse_args()

    plan_context = PlanContext.build(view=args.view, level=args.level,
                                     level_label=args.level, title=args.dxf_path)
    service = OpeningDetectionService(args.dxf_path, context=plan_context,
                                      unit_scale=args.scale)
    detected = service.detect_openings()
    service.export_json(detected, args.output)

    def fmt(value):
        return "%.2f" % value if value is not None else "-"

    print("\n=== %d ouverture(s) détectée(s) (vue %s) ===" % (len(detected), plan_context.view))
    for o in detected:
        print("  %-32s %-13s l=%5s ep=%5s h=%5s allège=%5s  %-6s pos=%6s  clé=%s"
              % (o.name, o.opening_type, fmt(o.width), fmt(o.thickness),
                 fmt(o.height), fmt(o.sill_height), o.orientation or "-",
                 fmt(o.facade_offset), o.match_key))
