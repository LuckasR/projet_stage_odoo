# -*- coding: utf-8 -*-
"""
plan_analysis.py
================

Socle commun aux services d'analyse de plans (murs, semelles...).

Il regroupe ce qui ne dépend pas de l'ouvrage recherché :

    - le classement du plan importé : type de plan, type de vue, niveau
      (`PlanContext`) et la normalisation des libellés saisis librement ;
    - la lecture géométrique d'un DXF (`DxfPlanReader`) : segments d'un
      calque, contours fermés, textes, et la détection des paires de
      segments parallèles qui décrit tout ouvrage linéaire — un mur comme
      une semelle filante ou une longrine.

Chaque service métier (wall_detection_service, footing_detection_service)
part de ce socle et n'écrit que ses propres règles : calques à lire,
dimensions plausibles, et traduction vers son modèle Odoo.

Dépendances :
    pip install ezdxf shapely
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import ezdxf
from shapely.geometry import LineString, Point

logger = logging.getLogger("plan_analysis")


# ============================================================
# TYPES DE VUE
# ============================================================

VIEW_PLAN = "plan"
VIEW_SECTION = "coupe"
VIEW_ELEVATION = "facade"
VIEW_DETAIL = "detail"
VIEW_SCHEMA = "schema"
VIEW_3D = "3d"

# Vues porteuses d'une géométrie exploitable, tous ouvrages confondus.
# Chaque service restreint ensuite à ce qu'il sait lire.
GEOMETRIC_VIEWS = (VIEW_PLAN, VIEW_ELEVATION, VIEW_SECTION)

_VIEW_ALIASES: Dict[str, Tuple[str, ...]] = {
    VIEW_SECTION: ("coupe", "section"),
    VIEW_ELEVATION: ("facade", "elevation"),
    VIEW_DETAIL: ("detail",),
    VIEW_SCHEMA: ("schema", "diagramme"),
    VIEW_3D: ("3d", "perspective", "axonometrie", "isometrie"),
    VIEW_PLAN: ("plan", "vue de dessus", "top view"),
}

ORIENTATIONS = ("nord", "sud", "est", "ouest")

_ORIENTATION_ALIASES: Dict[str, Tuple[str, ...]] = {
    "nord": ("nord", "north"),
    "sud": ("sud", "south"),
    "est": ("est", "east"),
    "ouest": ("ouest", "west"),
}

# Clé de rapprochement « s'applique à tout le niveau » : utilisée par les
# vues qui renseignent une caractéristique commune (coupe -> hauteur sous
# plafond) sans pouvoir désigner un ouvrage précis.
LEVEL_WILDCARD = "*"

# Profondeur maximale d'imbrication de blocs suivie à l'explosion : au-delà,
# on est dans du symbole décoratif, pas dans de l'ouvrage.
MAX_BLOCK_DEPTH = 3

# Marge au-delà de laquelle un ouvrage est jugé « linéaire » plutôt que
# ponctuel : sa longueur doit dépasser sa largeur de plus que l'erreur
# d'arrondi du dessin.
SQUARENESS_MARGIN = 1.000001


def normalize_text(value: Optional[str]) -> str:
    """Minuscules, sans accents, espaces normalisés — pour comparer des
    libellés saisis librement par l'utilisateur (« Façade », « FACADE »)."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


def normalize_view(value: Optional[str]) -> str:
    """Ramène un code ou un libellé de vue à l'une des constantes VIEW_*.
    Retourne VIEW_PLAN par défaut : c'est la vue historique du module."""
    text = normalize_text(value)
    if not text:
        return VIEW_PLAN
    # Les vues spécifiques sont testées AVANT la vue en plan : un libellé
    # comme « Plan de coupe » ou « Plan de façade » désigne une coupe ou une
    # façade, pas une vue de dessus. D'où l'ordre de _VIEW_ALIASES.
    for view, aliases in _VIEW_ALIASES.items():
        if any(alias in text for alias in aliases):
            return view
    logger.info("Type de vue inconnu (%r) : traité comme une vue en plan", value)
    return VIEW_PLAN


def find_orientation(*texts: Optional[str]) -> Optional[str]:
    """Première orientation cardinale trouvée dans les textes fournis
    (titre du plan, cartouche, textes du DXF).

    Le test se fait sur des mots entiers : « est » ne doit pas matcher dans
    « ouest », ni dans un nom de fichier comme « chantier-test »."""
    for raw in texts:
        text = normalize_text(raw)
        if not text:
            continue
        for orientation, aliases in _ORIENTATION_ALIASES.items():
            if any(re.search(r'\b%s\b' % re.escape(alias), text) for alias in aliases):
                return orientation
    return None


# ============================================================
# CONTEXTE DE CLASSIFICATION DU PLAN
# ============================================================

@dataclass
class PlanContext:
    """Classement du plan importé : ce que la vue permet de voir, et à quel
    niveau du bâtiment cela se rapporte."""

    view: str = VIEW_PLAN
    level: Optional[str] = None          # clé normalisée du niveau (« r+0 »)
    level_label: Optional[str] = None    # libellé affiché (« R+0 »)
    plan_types: Tuple[str, ...] = ()
    title: Optional[str] = None          # nom du fichier / du plan

    @classmethod
    def build(cls, view=None, level=None, level_label=None,
              plan_types: Sequence[str] = (), title=None) -> "PlanContext":
        return cls(
            view=normalize_view(view),
            level=normalize_text(level) or None,
            level_label=level_label or level or None,
            plan_types=tuple(normalize_text(p) for p in plan_types if p),
            title=title,
        )

    def match_key(self, suffix: str) -> str:
        """Clé d'identité d'un ouvrage : (niveau, désignation). Deux plans du
        même niveau décrivant le même ouvrage produisent la même clé."""
        return "%s|%s" % (self.level or "-", suffix)

    @property
    def is_supported(self) -> bool:
        """Vue porteuse d'une géométrie exploitable (plan, façade, coupe)."""
        return self.view in GEOMETRIC_VIEWS


# ============================================================
# LECTURE GÉOMÉTRIQUE D'UN DXF
# ============================================================

@dataclass
class Outline:
    """Contour fermé (polyligne) et sa boîte englobante."""

    minx: float
    miny: float
    maxx: float
    maxy: float
    layer: str
    points: List[Tuple[float, float]]

    @property
    def width(self) -> float:
        return self.maxx - self.minx

    @property
    def height(self) -> float:
        return self.maxy - self.miny

    @property
    def center(self) -> Tuple[float, float]:
        return (self.minx + self.maxx) / 2.0, (self.miny + self.maxy) / 2.0


@dataclass
class ParallelPair:
    """Deux segments parallèles et l'ouvrage linéaire qu'ils encadrent :
    l'axe médian, et leur écartement (épaisseur du mur, largeur de la
    semelle filante...)."""

    axis: LineString
    width: float
    layer_a: str
    layer_b: str

    @property
    def length(self) -> float:
        return self.axis.length

    @property
    def ends(self):
        (sx, sy), (ex, ey) = self.axis.coords[0], self.axis.coords[-1]
        return sx, sy, ex, ey

    @property
    def center(self) -> Tuple[float, float]:
        sx, sy, ex, ey = self.ends
        return (sx + ex) / 2.0, (sy + ey) / 2.0


class DxfPlanReader:
    """Accès géométrique à un DXF, calque par calque.

    Les services métier n'appellent jamais ezdxf directement : ils demandent
    ici des segments, des contours ou des paires parallèles."""

    def __init__(self, dxf_path: str):
        self.dxf_path = dxf_path
        self.doc = ezdxf.readfile(dxf_path)
        self.msp = self.doc.modelspace()
        self._block_content: Optional[List[Tuple[object, str]]] = None

    # --------------------------------------------------------
    # Contenu des blocs insérés (INSERT)
    # --------------------------------------------------------

    def block_entities(self) -> List[Tuple[object, str]]:
        """(entité, calque) de tout ce que contiennent les blocs insérés.

        Un ouvrage répétitif — poteau, semelle, symbole — est très souvent
        dessiné UNE fois comme bloc, puis inséré à chaque emplacement. Sa
        géométrie n'est alors pas dans le modelspace : une recherche par
        calque ne la voit pas, et l'ouvrage passe pour absent du plan.

        `virtual_entities()` rend des copies déjà transformées (position,
        échelle et rotation de l'insertion appliquées), donc directement
        exploitables dans le repère du dessin.

        Convention DXF respectée ici : une entité placée sur le calque « 0 »
        à l'intérieur d'un bloc prend le calque de l'insertion."""
        if self._block_content is not None:
            return self._block_content

        content: List[Tuple[object, str]] = []
        stack = [(insert, MAX_BLOCK_DEPTH) for insert in self.msp.query("INSERT")]

        while stack:
            insert, depth = stack.pop()
            host_layer = insert.dxf.get("layer", "0")
            try:
                children = list(insert.virtual_entities())
            except Exception as exc:
                logger.debug("Bloc %s illisible : %s",
                             insert.dxf.get("name", "?"), exc)
                continue

            for child in children:
                if child.dxftype() == "INSERT":
                    if depth > 1:
                        stack.append((child, depth - 1))
                    continue
                layer = child.dxf.get("layer", "0")
                content.append((child, host_layer if layer == "0" else layer))

        if content:
            logger.info("%d entité(s) lues dans les blocs insérés", len(content))
        self._block_content = content
        return content

    @staticmethod
    def polyline_points(entity):
        """(sommets, fermée) d'une LWPOLYLINE ou d'une POLYLINE ; None sinon."""
        dxftype = entity.dxftype()
        try:
            if dxftype == "LWPOLYLINE":
                return [(p[0], p[1]) for p in entity.get_points()], bool(entity.closed)
            if dxftype == "POLYLINE":
                return ([(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices],
                        bool(entity.is_closed))
        except Exception as exc:
            logger.debug("Polyligne illisible (%s) : %s", dxftype, exc)
        return None

    def _block_segments(self, layers: Sequence[str]) -> List[Tuple[LineString, str]]:
        wanted = set(layers)
        segments: List[Tuple[LineString, str]] = []

        for entity, layer in self.block_entities():
            if layer not in wanted:
                continue
            if entity.dxftype() == "LINE":
                start = (entity.dxf.start.x, entity.dxf.start.y)
                end = (entity.dxf.end.x, entity.dxf.end.y)
                if start != end:
                    segments.append((LineString([start, end]), layer))
                continue
            points = self.polyline_points(entity)
            if points:
                segments.extend(self.polyline_to_segments(points[0], points[1], layer))

        return segments

    def _block_outlines(self, layers: Sequence[str]) -> List[Outline]:
        wanted = set(layers)
        outlines: List[Outline] = []

        for entity, layer in self.block_entities():
            if layer not in wanted:
                continue
            points = self.polyline_points(entity)
            if not points or not points[1]:
                continue
            outline = self._to_outline(points[0], layer)
            if outline:
                outlines.append(outline)

        return outlines

    # --------------------------------------------------------
    # Segments
    # --------------------------------------------------------

    def collect_segments(self, layers: Sequence[str],
                         include_blocks: bool = False
                         ) -> List[Tuple[LineString, str]]:
        """Tous les segments des entités LINE, LWPOLYLINE et POLYLINE situées
        sur les calques demandés. Les polylignes (fermées ou non) sont
        décomposées en segments : un ouvrage dessiné comme contour fermé et un
        ouvrage dessiné trait par trait donnent alors la même matière.

        `include_blocks` ajoute ce que contiennent les blocs insérés
        (cf. `block_entities`)."""
        segments: List[Tuple[LineString, str]] = []

        for layer_name in layers:
            try:
                for e in self.msp.query(f'LINE[layer=="{layer_name}"]'):
                    s = (e.dxf.start.x, e.dxf.start.y)
                    t = (e.dxf.end.x, e.dxf.end.y)
                    if s != t:
                        segments.append((LineString([s, t]), layer_name))
            except Exception as exc:
                logger.debug("Erreur LINE[%s] : %s", layer_name, exc)

            try:
                for e in self.msp.query(f'LWPOLYLINE[layer=="{layer_name}"]'):
                    pts = [(p[0], p[1]) for p in e.get_points()]
                    segments.extend(
                        self.polyline_to_segments(pts, bool(e.closed), layer_name))
            except Exception as exc:
                logger.debug("Erreur LWPOLYLINE[%s] : %s", layer_name, exc)

            # POLYLINE : ancien format R12, encore très courant
            try:
                for e in self.msp.query(f'POLYLINE[layer=="{layer_name}"]'):
                    pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    segments.extend(
                        self.polyline_to_segments(pts, bool(e.is_closed), layer_name))
            except Exception as exc:
                logger.debug("Erreur POLYLINE[%s] : %s", layer_name, exc)

        if include_blocks:
            segments.extend(self._block_segments(layers))
        return segments

    @staticmethod
    def polyline_to_segments(
        points: Sequence[Tuple[float, float]], closed: bool, layer: str
    ) -> List[Tuple[LineString, str]]:
        """Décompose une liste de sommets en segments (LineString)."""
        out: List[Tuple[LineString, str]] = []
        if not points:
            return out

        pts = list(points)
        if closed and pts[0] != pts[-1]:
            pts = pts + [pts[0]]

        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            if p1 == p2:
                continue
            seg = LineString([p1, p2])
            if seg.length > 1e-6:
                out.append((seg, layer))
        return out

    # --------------------------------------------------------
    # Contours fermés et textes
    # --------------------------------------------------------

    def collect_closed_outlines(self, layers: Sequence[str],
                                include_blocks: bool = False) -> List[Outline]:
        """Contours fermés des calques demandés. C'est ainsi que sont dessinés
        les ouvrages ponctuels (semelle isolée vue en plan) et les ouvrages
        coupés (mur en façade ou en coupe).

        `include_blocks` ajoute les contours dessinés dans un bloc inséré
        (cf. `block_entities`)."""
        outlines: List[Outline] = []

        for layer_name in layers:
            try:
                for e in self.msp.query(f'LWPOLYLINE[layer=="{layer_name}"]'):
                    if not e.closed:
                        continue
                    pts = [(p[0], p[1]) for p in e.get_points()]
                    outline = self._to_outline(pts, layer_name)
                    if outline:
                        outlines.append(outline)
            except Exception as exc:
                logger.debug("Erreur contours LWPOLYLINE[%s] : %s", layer_name, exc)

            try:
                for e in self.msp.query(f'POLYLINE[layer=="{layer_name}"]'):
                    if not e.is_closed:
                        continue
                    pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    outline = self._to_outline(pts, layer_name)
                    if outline:
                        outlines.append(outline)
            except Exception as exc:
                logger.debug("Erreur contours POLYLINE[%s] : %s", layer_name, exc)

        if include_blocks:
            outlines.extend(self._block_outlines(layers))
        return outlines

    @classmethod
    def _to_outline(cls, points, layer: str) -> Optional[Outline]:
        box = cls.bounding_box(points)
        if not box:
            return None
        return Outline(*box, layer=layer, points=list(points))

    def collect_texts(self) -> List[str]:
        """Textes du dessin (TEXT / MTEXT) : cartouche, titres de vue, repères."""
        texts: List[str] = []
        for dxftype in ("TEXT", "MTEXT"):
            try:
                for e in self.msp.query(dxftype):
                    raw = getattr(e, "plain_text", None)
                    value = raw() if callable(raw) else e.dxf.get("text", "")
                    if value:
                        texts.append(value)
            except Exception as exc:
                logger.debug("Erreur collecte %s : %s", dxftype, exc)
        return texts

    def collect_texts_with_position(self) -> List[Tuple[str, float, float]]:
        """Idem, avec la position d'insertion : sert à rattacher un repère
        (« S1 ») à l'ouvrage qu'il désigne, par proximité."""
        texts: List[Tuple[str, float, float]] = []
        for dxftype in ("TEXT", "MTEXT"):
            try:
                for e in self.msp.query(dxftype):
                    raw = getattr(e, "plain_text", None)
                    value = raw() if callable(raw) else e.dxf.get("text", "")
                    if not value:
                        continue
                    point = e.dxf.get("insert", None)
                    if point is None:
                        continue
                    texts.append((value, point.x, point.y))
            except Exception as exc:
                logger.debug("Erreur collecte positionnée %s : %s", dxftype, exc)
        return texts

    # --------------------------------------------------------
    # Boîtes englobantes
    # --------------------------------------------------------

    @staticmethod
    def bounding_box(points: Iterable[Tuple[float, float]]):
        pts = list(points)
        if len(pts) < 2:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    @classmethod
    def segments_bounding_box(cls, segments: Sequence[Tuple[LineString, str]]):
        points = []
        for line, _layer in segments:
            points.extend(line.coords)
        return cls.bounding_box(points)

    # --------------------------------------------------------
    # Ouvrages linéaires : paires de segments parallèles
    # --------------------------------------------------------

    @staticmethod
    def line_angle(line: LineString) -> float:
        (x1, y1), (x2, y2) = line.coords[0], line.coords[-1]
        return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180

    @staticmethod
    def overlap_length(line_a: LineString, line_b: LineString) -> float:
        """Longueur de recouvrement longitudinal entre 2 segments parallèles."""
        proj = [line_a.project(Point(c)) for c in line_b.coords]
        lo = max(0.0, min(proj))
        hi = min(line_a.length, max(proj))
        return max(0.0, hi - lo)

    @staticmethod
    def center_axis(line_a: LineString, line_b: LineString) -> LineString:
        """Axe médian entre 2 segments parallèles."""
        a1, a2 = line_a.coords[0], line_a.coords[-1]
        b_proj1 = line_b.interpolate(line_b.project(Point(a1)))
        b_proj2 = line_b.interpolate(line_b.project(Point(a2)))
        mid1 = ((a1[0] + b_proj1.x) / 2.0, (a1[1] + b_proj1.y) / 2.0)
        mid2 = ((a2[0] + b_proj2.x) / 2.0, (a2[1] + b_proj2.y) / 2.0)
        return LineString([mid1, mid2])

    @classmethod
    def find_parallel_pairs(
        cls,
        segments: Sequence[Tuple[LineString, str]],
        min_width: float,
        max_width: float,
        min_length: float,
        angle_tolerance: float = 2.0,
    ) -> List[ParallelPair]:
        """Paires de segments parallèles écartés d'une largeur plausible :
        c'est la signature de tout ouvrage linéaire vu en plan (mur, semelle
        filante, longrine). L'axe médian de la paire est l'axe de l'ouvrage.

        Les deux garde-fous qui évitent les faux positifs : un recouvrement
        longitudinal suffisant, et un ouvrage plus long que large — sans quoi
        les deux bouts d'un même ouvrage formeraient une paire."""
        pairs: List[ParallelPair] = []
        n = len(segments)

        for i in range(n):
            line_a, layer_a = segments[i]
            if line_a.length < min_length:
                continue
            angle_a = cls.line_angle(line_a)

            for j in range(i + 1, n):
                line_b, layer_b = segments[j]
                if line_b.length < min_length:
                    continue

                angle_b = cls.line_angle(line_b)
                angle_diff = min(abs(angle_a - angle_b), 180 - abs(angle_a - angle_b))
                if angle_diff > angle_tolerance:
                    continue

                width = line_a.distance(line_b)
                if not (min_width <= width <= max_width):
                    continue

                overlap = cls.overlap_length(line_a, line_b)
                # Franchement plus long que large : sans la marge, les deux
                # bords opposés d'un carré passent le test à l'arrondi près
                # et un ouvrage ponctuel ressort comme ouvrage linéaire.
                if overlap < min_length or overlap <= width * SQUARENESS_MARGIN:
                    continue

                axis = cls.center_axis(line_a, line_b)
                if axis.length < min_length:
                    continue

                pairs.append(ParallelPair(axis=axis, width=width,
                                          layer_a=layer_a, layer_b=layer_b))

        return pairs
