# -*- coding: utf-8 -*-
"""
formwork_detection_service.py
=============================

Détection des ouvrages d'un plan de COFFRAGE (plan d'exécution), vue en plan :

    S-POT          poteau       contour fermé de la section
                                -> côté X x côté Y, position
    S-POU          poutre       bande entre deux bords parallèles, découpée
    S-POU-CACHE                 en travées par les poteaux qui la portent
                                -> portée (entre axes d'appui), largeur
    S-DAL          dalle        contour fermé du plancher, moins les trémies
    S-TREMIE                    -> surface nette, épaisseur lue dans le
                                   repère (« D01 - Hourdis 16+4 - ep. 20 cm »)
    S-REF          mur          fond de plan des murs du niveau : bandes entre
                                deux bords parallèles, réunies par-dessus les
                                baies -> longueur, épaisseur

    S-DAL-SYMB     sens de portée du plancher : sans métré, non exploité.

La nomenclature du plan (« Poutre BA | 30x40 ») donne la hauteur des
poutres, que la vue en plan ne montre pas. La hauteur des poteaux et des
murs n'y figure pas : elle vient du plan de détail (coupes), cf.
`detail_analysis_service`, ou se saisit à la validation.

Le résultat suit le format de `construction.analysis._analyze_plan` : il
alimente les brouillons d'éléments, validés avant création des éléments,
des tâches et des phases.
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from shapely.geometry import Polygon

try:
    from .plan_analysis import VIEW_PLAN, DxfPlanReader, PlanContext, normalize_text
except ImportError:  # exécution directe du module en ligne de commande
    from plan_analysis import (  # type: ignore[no-redef]
        VIEW_PLAN, DxfPlanReader, PlanContext, normalize_text)

logger = logging.getLogger("formwork_detection_service")


# ============================================================
# CONFIGURATION
# ============================================================

COLUMN_LAYER = "S-POT"
BEAM_LAYERS = ("S-POU", "S-POU-CACHE")
SLAB_LAYER = "S-DAL"
SLAB_OPENING_LAYER = "S-TREMIE"
WALL_LAYERS = ("S-REF",)

FORMWORK_LAYERS = (COLUMN_LAYER,) + BEAM_LAYERS + (SLAB_LAYER,) + WALL_LAYERS

# Codes de construction.element.type
TYPE_COLUMN = "poteau"
TYPE_BEAM = "poutre"
TYPE_SLAB = "dalle"
TYPE_WALL = "mur"

KEY_PREFIXES = {TYPE_COLUMN: "POT", TYPE_BEAM: "POU", TYPE_SLAB: "DAL",
                TYPE_WALL: "MUR"}

# Dimensions plausibles, en mètres
MIN_COLUMN_SIDE = 0.15
MAX_COLUMN_SIDE = 1.50
MAX_COLUMN_RATIO = 6.0

MIN_BEAM_WIDTH = 0.12
MAX_BEAM_WIDTH = 0.80
MIN_BEAM_SPAN = 0.50

MIN_WALL_THICKNESS = 0.05
MAX_WALL_THICKNESS = 0.40
MIN_WALL_LENGTH = 0.30
# Interruption d'un mur franchie lors de la réunion des tronçons : une baie
# (porte, fenêtre) ou la rencontre d'un mur perpendiculaire.
MAX_WALL_GAP = 3.00
# En deçà, l'interruption est la rencontre d'un mur perpendiculaire, pas une
# baie : elle n'est pas comptée dans les ouvertures du mur.
MIN_OPENING_WIDTH = 0.50

MIN_SLAB_AREA = 1.0

PARALLEL_ANGLE_TOLERANCE = 2.0
# Deux bandes sont sur le même axe si leurs décalages diffèrent de moins que ça
SAME_AXIS_TOLERANCE = 0.02
# Poteau retenu comme appui d'une poutre s'il déborde au plus de ça au-delà
# de l'extrémité de la bande (la bande s'arrête au nu du poteau)
SUPPORT_END_TOLERANCE = 0.50

MAX_LABEL_DISTANCE = 1.20

LABEL_PATTERNS = {
    TYPE_COLUMN: re.compile(r"^\s*((?:POT|PO|P)[\s\-_]?\d+[A-Za-z]?)\s*$", re.I),
    TYPE_BEAM: re.compile(r"^\s*((?:POU|PT|B)[\s\-_]?\d+[A-Za-z]?)\s*$", re.I),
    # « D01 - Hourdis 16+4 - ep. 20 cm » : le repère ouvre le libellé
    TYPE_SLAB: re.compile(r"^\s*((?:DAL|PL|D)[\s\-_]?\d+[A-Za-z]?)\b", re.I),
}

# « ep. 20 cm », « ép 0.20 m », « e=20 »
THICKNESS_PATTERN = re.compile(
    r"\b(?:ep|e)\s*[.=:]?\s*(\d+(?:[.,]\d+)?)\s*(cm|m)?\b", re.I)
# Plancher à entrevous : « Hourdis 16+4 » = 20 cm
HOURDIS_PATTERN = re.compile(r"\b(\d{1,2})\s*\+\s*(\d{1,2})\b")
# Section de nomenclature : « 30x40 » (cm)
SECTION_PATTERN = re.compile(r"^\s*(\d{2,3})\s*[xX×*]\s*(\d{2,3})\s*(?:cm)?\s*$")

# Mot de la ligne de nomenclature -> type d'ouvrage (le plus précis d'abord)
NOMENCLATURE_KEYWORDS = (
    ("semelle filante", "semelle_filante"),
    ("semelle", "semelle"),
    ("longrine", "longrine"),
    ("poutre", TYPE_BEAM),
    ("poteau", TYPE_COLUMN),
    ("voile", TYPE_WALL),
)
SLAB_KEYWORDS = ("hourdis", "dalle", "plancher", "prédalle", "predalle")

DEDUP_TOLERANCE = 0.05


# ============================================================
# LECTURE COMMUNE : textes et bandes parallèles
# ============================================================

@dataclass
class PlacedText:
    text: str
    x: float
    y: float
    height: float
    layer: str


@dataclass
class Band:
    """Ouvrage linéaire vu en plan : un axe (direction `u`, décalage
    `offset` sur la normale), une étendue [lo, hi] le long de l'axe et une
    largeur. Les interruptions franchies à la réunion sont gardées dans
    `gaps` (baies d'un mur)."""

    angle: float
    offset: float
    lo: float
    hi: float
    width: float
    gaps: List[Tuple[float, float]] = field(default_factory=list)

    @property
    def u(self) -> Tuple[float, float]:
        a = math.radians(self.angle)
        return math.cos(a), math.sin(a)

    @property
    def n(self) -> Tuple[float, float]:
        a = math.radians(self.angle)
        return -math.sin(a), math.cos(a)

    @property
    def length(self) -> float:
        return self.hi - self.lo

    def gap_length(self, min_gap: float = 0.0) -> float:
        return sum(b - a for a, b in self.gaps if b - a >= min_gap)

    def point(self, t: float) -> Tuple[float, float]:
        (ux, uy), (nx, ny) = self.u, self.n
        return t * ux + self.offset * nx, t * uy + self.offset * ny

    def frame(self, x: float, y: float) -> Tuple[float, float]:
        """(abscisse le long de l'axe, écart à l'axe) d'un point."""
        (ux, uy), (nx, ny) = self.u, self.n
        return x * ux + y * uy, x * nx + y * ny - self.offset


class ExecutionPlanReader(DxfPlanReader):
    """Lecture partagée par les plans d'exécution (coffrage, détails)."""

    def placed_texts(self) -> List[PlacedText]:
        """TEXT / MTEXT avec position, hauteur et calque. Pour un texte
        justifié, la position retenue est le point d'alignement : c'est lui
        que le dessinateur a placé."""
        if getattr(self, "_placed_texts", None) is not None:
            return self._placed_texts
        out: List[PlacedText] = []
        for e in self.msp.query("TEXT MTEXT"):
            try:
                if e.dxftype() == "MTEXT":
                    value, height = e.plain_text(), e.dxf.get("char_height", 0.0)
                    point = e.dxf.insert
                else:
                    value, height = e.dxf.get("text", ""), e.dxf.get("height", 0.0)
                    aligned = e.dxf.get("halign", 0) or e.dxf.get("valign", 0)
                    point = e.dxf.get("align_point") if aligned else None
                    point = point or e.dxf.insert
            except Exception as exc:  # noqa: BLE001
                logger.debug("Texte illisible : %s", exc)
                continue
            if value and value.strip():
                out.append(PlacedText(value.strip(), point.x, point.y,
                                      height or 0.0, e.dxf.get("layer", "0")))
        self._placed_texts = out
        return out

    def same_row(self, ref: PlacedText) -> List[PlacedText]:
        """Textes alignés sur la même ligne qu'un texte (ligne de tableau)."""
        tolerance = max(ref.height * 0.6, 1e-3)
        return [t for t in self.placed_texts()
                if t is not ref and abs(t.y - ref.y) <= tolerance]

    # --------------------------------------------------------
    # Bandes : paires de bords parallèles, axe par axe
    # --------------------------------------------------------

    @staticmethod
    def find_bands(segments, min_width: float, max_width: float,
                   min_length: float,
                   angle_tolerance: float = PARALLEL_ANGLE_TOLERANCE) -> List[Band]:
        """Une bande par paire de bords parallèles, limitée à leur
        recouvrement : contrairement à l'axe médian classique, l'étendue ne
        déborde jamais du plus court des deux bords."""
        prepared = []
        for line, _layer in segments:
            (x1, y1), (x2, y2) = line.coords[0], line.coords[-1]
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
            prepared.append((angle, x1, y1, x2, y2, line.length))

        bands: List[Band] = []
        for i, (ang_a, ax1, ay1, ax2, ay2, len_a) in enumerate(prepared):
            if len_a < min_length:
                continue
            a = math.radians(ang_a)
            ux, uy, nx, ny = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
            off_a = ax1 * nx + ay1 * ny
            ta = sorted((ax1 * ux + ay1 * uy, ax2 * ux + ay2 * uy))

            for ang_b, bx1, by1, bx2, by2, len_b in prepared[i + 1:]:
                if len_b < min_length:
                    continue
                diff = abs(ang_a - ang_b)
                if min(diff, 180 - diff) > angle_tolerance:
                    continue
                off_b = (bx1 * nx + by1 * ny + bx2 * nx + by2 * ny) / 2.0
                width = abs(off_b - off_a)
                if not (min_width <= width <= max_width):
                    continue
                tb = sorted((bx1 * ux + by1 * uy, bx2 * ux + by2 * uy))
                lo, hi = max(ta[0], tb[0]), min(ta[1], tb[1])
                if hi - lo < min_length or hi - lo <= width:
                    continue
                bands.append(Band(ang_a, (off_a + off_b) / 2.0, lo, hi, width))
        return bands

    @staticmethod
    def merge_bands(bands: Sequence[Band], max_gap: float) -> List[Band]:
        """Réunit les bandes portées par le même axe et de même largeur,
        par-dessus les interruptions de moins de `max_gap`."""
        groups: List[List[Band]] = []
        for band in sorted(bands, key=lambda b: (round(b.angle), b.offset, b.lo)):
            for group in groups:
                ref = group[0]
                diff = abs(ref.angle - band.angle)
                if (min(diff, 180 - diff) <= PARALLEL_ANGLE_TOLERANCE
                        and abs(ref.offset - band.offset) <= SAME_AXIS_TOLERANCE
                        and abs(ref.width - band.width) <= SAME_AXIS_TOLERANCE):
                    group.append(band)
                    break
            else:
                groups.append([band])

        merged: List[Band] = []
        for group in groups:
            group.sort(key=lambda b: b.lo)
            current = Band(group[0].angle, group[0].offset, group[0].lo,
                           group[0].hi, group[0].width)
            for band in group[1:]:
                if band.lo <= current.hi + 1e-6:
                    current.hi = max(current.hi, band.hi)
                elif band.lo - current.hi <= max_gap:
                    current.gaps.append((current.hi, band.lo))
                    current.hi = band.hi
                else:
                    merged.append(current)
                    current = Band(band.angle, band.offset, band.lo, band.hi, band.width)
            merged.append(current)
        return merged


# ============================================================
# STRUCTURE DE DONNÉES
# ============================================================

@dataclass
class DetectedFormwork:
    """Ouvrage relevé sur le plan de coffrage, déjà en mètres."""

    key: str
    type_code: str
    layer: str
    center_x: float
    center_y: float
    bbox: Tuple[float, float, float, float]
    dimensions: Dict[str, float]
    quantities: Dict[str, float] = field(default_factory=dict)
    level: Optional[str] = None
    label_found: bool = False
    confidence: float = 0.0
    issues: List[str] = field(default_factory=list)
    # Axe (x1, y1, x2, y2) en unités du dessin, pour un ouvrage linéaire :
    # c'est lui qui devient l'objet construction.wall d'un mur.
    axis: Optional[Tuple[float, float, float, float]] = None
    # Baies d'un mur : interruptions de son tracé, chacune (x1, y1, x2, y2)
    # sur l'axe, en unités du dessin. Elles deviennent des construction.opening
    # rattachées au mur.
    openings: List[Tuple[float, float, float, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_analysis_item(self) -> dict:
        return {
            "key": self.key,
            "type": self.type_code,
            "level": self.level or False,
            "quantities": {k: round(v, 3) for k, v in self.quantities.items()},
            # Valeurs numériques arrondies ; la liste des trémies telle quelle.
            "dimensions": {k: round(v, 3) if isinstance(v, (int, float)) else v
                           for k, v in self.dimensions.items()},
            "confidence": round(min(max(self.confidence, 0.0), 0.95), 2),
            "issue": " ; ".join(self.issues) or False,
            "source": {"page": 1, "bbox": list(self.bbox)},
        }


# ============================================================
# SERVICE PRINCIPAL
# ============================================================

class FormworkDetectionService(ExecutionPlanReader):
    """Lit un plan de coffrage et en extrait poteaux, poutres, dalles et
    murs. `unit_scale` convertit les unités du dessin en mètres."""

    SUPPORTED_VIEWS = (VIEW_PLAN,)

    def __init__(self, dxf_path: str, context: Optional[PlanContext] = None,
                 unit_scale: float = 1.0):
        super().__init__(dxf_path)
        self.context = context or PlanContext()
        self.unit_scale = unit_scale or 1.0
        self._placed_texts = None
        self._sections: Optional[Dict[str, Tuple[float, float]]] = None

    # --------------------------------------------------------
    # POINT D'ENTRÉE
    # --------------------------------------------------------

    def detect(self) -> List[DetectedFormwork]:
        ctx = self.context
        logger.info("Plan de coffrage %s (vue=%s, niveau=%s)",
                    self.dxf_path, ctx.view, ctx.level_label or "-")
        if ctx.view not in self.SUPPORTED_VIEWS:
            logger.info("Vue « %s » : un coffrage se lit en vue en plan, "
                        "aucune détection lancée", ctx.view)
            return []

        columns = self._detect_columns()
        items = (columns
                 + self._detect_beams(columns)
                 + self._detect_slabs()
                 + self._detect_walls())
        items = self._deduplicate(items)
        for item in items:
            item.level = ctx.level_label
        logger.info("Coffrage : %d ouvrage(s) détecté(s)", len(items))
        return items

    def to_analysis_result(self, items: List[DetectedFormwork]) -> dict:
        return {"schema_version": 1,
                "elements": [i.to_analysis_item() for i in items]}

    # --------------------------------------------------------
    # POTEAUX
    # --------------------------------------------------------

    def _detect_columns(self) -> List[DetectedFormwork]:
        s = self.unit_scale
        found = []
        for outline in self.collect_closed_outlines([COLUMN_LAYER], include_blocks=True):
            a, b = sorted((outline.width * s, outline.height * s))
            if a < MIN_COLUMN_SIDE or b > MAX_COLUMN_SIDE or b / a > MAX_COLUMN_RATIO:
                continue
            found.append(DetectedFormwork(
                key="", type_code=TYPE_COLUMN, layer=outline.layer,
                center_x=outline.center[0], center_y=outline.center[1],
                bbox=(outline.minx, outline.miny, outline.maxx, outline.maxy),
                dimensions={"l": outline.width * s, "w": outline.height * s},
                confidence=0.75,
                issues=["Hauteur non lisible sur le coffrage : reprise du plan "
                        "de détail (coupes) ou à saisir"],
            ))
        self._label(found, TYPE_COLUMN)
        logger.info("Calque %s : %d poteau(x)", COLUMN_LAYER, len(found))
        return found

    # --------------------------------------------------------
    # POUTRES : bandes découpées en travées par leurs poteaux
    # --------------------------------------------------------

    def _detect_beams(self, columns: List[DetectedFormwork]) -> List[DetectedFormwork]:
        s = self.unit_scale
        segments = self.collect_segments(list(BEAM_LAYERS), include_blocks=True)
        if not segments:
            return []
        bands = self.merge_bands(
            self.find_bands(segments, MIN_BEAM_WIDTH / s, MAX_BEAM_WIDTH / s,
                            MIN_BEAM_SPAN / s),
            max_gap=MAX_BEAM_WIDTH / s)

        section = self.nomenclature_sections().get(TYPE_BEAM)
        found: List[DetectedFormwork] = []
        for band in bands:
            for lo, hi in self._spans(band, columns):
                if (hi - lo) * s < MIN_BEAM_SPAN:
                    continue
                x1, y1 = band.point(lo)
                x2, y2 = band.point(hi)
                dims = {"l": (hi - lo) * s, "w": band.width * s}
                issues = []
                if section:
                    dims["h"] = section[1]
                    if abs(section[0] - dims["w"]) > 0.02:
                        issues.append("Largeur dessinée %.2f m, nomenclature %.2f m"
                                      % (dims["w"], section[0]))
                else:
                    issues.append("Hauteur de poutre absente de la nomenclature : "
                                  "reprise du plan de détail ou à saisir")
                found.append(DetectedFormwork(
                    key="", type_code=TYPE_BEAM, layer=BEAM_LAYERS[0],
                    center_x=(x1 + x2) / 2.0, center_y=(y1 + y2) / 2.0,
                    bbox=(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)),
                    dimensions=dims,
                    quantities=self._beam_quantities(dims),
                    confidence=0.70, issues=issues,
                ))
        self._label(found, TYPE_BEAM)
        logger.info("Calques %s : %d bande(s) -> %d travée(s) de poutre",
                    "/".join(BEAM_LAYERS), len(bands), len(found))
        return found

    def _spans(self, band: Band, columns: List[DetectedFormwork]):
        """Travées d'une poutre : entre axes de ses appuis, comme la portée
        d'une nomenclature. Une extrémité sans poteau (console, appui sur
        mur) borne la travée au bout dessiné."""
        tolerance = SUPPORT_END_TOLERANCE / self.unit_scale
        supports = []
        for col in columns:
            t, d = band.frame(col.center_x, col.center_y)
            half = max(col.bbox[2] - col.bbox[0], col.bbox[3] - col.bbox[1]) / 2.0
            if abs(d) <= band.width / 2.0 + half and band.lo - tolerance <= t <= band.hi + tolerance:
                supports.append((t, half))
        supports.sort()

        bounds: List[float] = []
        if not supports or supports[0][0] - supports[0][1] > band.lo + 1e-6:
            bounds.append(band.lo)
        for t, _half in supports:
            if not bounds or t - bounds[-1] > DEDUP_TOLERANCE:
                bounds.append(t)
        if not supports or supports[-1][0] + supports[-1][1] < band.hi - 1e-6:
            bounds.append(band.hi)
        return list(zip(bounds, bounds[1:]))

    @staticmethod
    def _beam_quantities(dims: Dict[str, float]) -> Dict[str, float]:
        if not dims.get("h"):
            return {}
        l, w, h = dims["l"], dims["w"], dims["h"]
        # Fond de moule + deux joues
        return {"beton_m3": l * w * h, "coffrage_m2": (2 * h + w) * l}

    # --------------------------------------------------------
    # DALLES : contour moins trémies
    # --------------------------------------------------------

    def _detect_slabs(self) -> List[DetectedFormwork]:
        s = self.unit_scale
        openings = [Polygon(o.points) for o in
                    self.collect_closed_outlines([SLAB_OPENING_LAYER], include_blocks=True)
                    if len(o.points) >= 3]
        found = []
        for outline in self.collect_closed_outlines([SLAB_LAYER], include_blocks=True):
            if len(outline.points) < 3:
                continue
            poly = Polygon(outline.points).buffer(0)
            gross = poly.area * s * s
            if gross < MIN_SLAB_AREA:
                continue
            holes = [o for o in openings if poly.contains(o.representative_point())]
            hole_area = sum(o.area for o in holes) * s * s
            net = gross - hole_area
            tremies = [self._tremie(hole, outline) for hole in holes]

            label_text = self._slab_label(poly)
            thickness = self._thickness(label_text) or self._nomenclature_slab_thickness()
            dims = {"l": max(outline.width, outline.height) * s,
                    "w": min(outline.width, outline.height) * s}
            if hole_area:
                dims["tremie_m2"] = hole_area
                dims["tremies"] = tremies
            quantities = {"surface_m2": net}
            issues = []
            if thickness:
                dims["h"] = thickness
                quantities.update(beton_m3=net * thickness, coffrage_m2=net)
            else:
                issues.append("Épaisseur absente du repère et de la nomenclature : "
                              "reprise du plan de détail ou à saisir")
            item = DetectedFormwork(
                key="", type_code=TYPE_SLAB, layer=outline.layer,
                center_x=outline.center[0], center_y=outline.center[1],
                bbox=(outline.minx, outline.miny, outline.maxx, outline.maxy),
                dimensions=dims, quantities=quantities,
                confidence=0.75 + (0.05 if thickness else 0.0), issues=issues)
            match = LABEL_PATTERNS[TYPE_SLAB].match(label_text or "")
            if match:
                item.key, item.label_found = self._clean_label(match.group(1)), True
            found.append(item)
        self._label(found, TYPE_SLAB)
        logger.info("Calque %s : %d dalle(s)", SLAB_LAYER, len(found))
        return found

    def _tremie(self, hole: Polygon, slab) -> dict:
        """Trémie d'une dalle, pour l'afficher : position et taille en mètres
        depuis le coin bas-gauche de la dalle (schéma de l'élément), et boîte
        dans le repère du plan (visualiseur).

        Le schéma dessine la longueur `l` (plus grand côté) à l'horizontale :
        une dalle plus haute que large y est donc couchée, et ses trémies
        tournent avec elle (rotation d'un quart de tour)."""
        s = self.unit_scale
        minx, miny, maxx, maxy = hole.bounds
        x, y = minx - slab.minx, miny - slab.miny
        w, h = maxx - minx, maxy - miny
        if slab.height > slab.width:
            x, y, w, h = y, slab.width - (x + w), h, w
        return {
            "x": round(x * s, 3),
            "y": round(y * s, 3),
            "w": round(w * s, 3),
            "h": round(h * s, 3),
            "area": round(hole.area * s * s, 3),
            "bbox": [minx, miny, maxx, maxy],
        }

    def _slab_label(self, poly: Polygon) -> Optional[str]:
        """Libellé de la dalle : texte de son calque placé dans son contour,
        sinon tout texte « Dxx » qu'elle contient."""
        from shapely.geometry import Point
        inside = [t for t in self.placed_texts() if poly.contains(Point(t.x, t.y))]
        for text in sorted(inside, key=lambda t: t.layer != SLAB_LAYER):
            if LABEL_PATTERNS[TYPE_SLAB].match(text.text):
                return text.text
        return None

    @staticmethod
    def _thickness(text: Optional[str]) -> Optional[float]:
        if not text:
            return None
        match = THICKNESS_PATTERN.search(text)
        if match:
            value = float(match.group(1).replace(",", "."))
            unit = (match.group(2) or "").lower()
            return value if unit == "m" or (not unit and value < 1.0) else value / 100.0
        match = HOURDIS_PATTERN.search(text)
        if match and "hourdis" in normalize_text(text):
            return (int(match.group(1)) + int(match.group(2))) / 100.0
        return None

    # --------------------------------------------------------
    # MURS : fond de plan S-REF
    # --------------------------------------------------------

    def _detect_walls(self) -> List[DetectedFormwork]:
        s = self.unit_scale
        segments = self.collect_segments(list(WALL_LAYERS), include_blocks=True)
        if not segments:
            return []
        bands = self.merge_bands(
            self.find_bands(segments, MIN_WALL_THICKNESS / s, MAX_WALL_THICKNESS / s,
                            MIN_WALL_LENGTH / s),
            max_gap=MAX_WALL_GAP / s)

        found = []
        for band in bands:
            if band.length * s < MIN_WALL_LENGTH:
                continue
            x1, y1 = band.point(band.lo)
            x2, y2 = band.point(band.hi)
            dims = {"l": band.length * s, "ep": band.width * s}
            openings = [band.point(a) + band.point(b) for a, b in band.gaps
                        if b - a >= MIN_OPENING_WIDTH / s]
            if openings:
                dims["ouvertures_m"] = band.gap_length(MIN_OPENING_WIDTH / s) * s
            found.append(DetectedFormwork(
                key="", type_code=TYPE_WALL, layer=WALL_LAYERS[0],
                center_x=(x1 + x2) / 2.0, center_y=(y1 + y2) / 2.0,
                bbox=(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)),
                dimensions=dims, confidence=0.60, axis=(x1, y1, x2, y2),
                openings=openings,
                issues=["Mur relevé sur le fond de plan du coffrage : à confirmer",
                        "Hauteur non lisible sur le coffrage : reprise du plan "
                        "de détail (coupes) ou à saisir"],
            ))
        self._label(found, TYPE_WALL)
        logger.info("Calque(s) %s : %d mur(s)", "/".join(WALL_LAYERS), len(found))
        return found

    # --------------------------------------------------------
    # NOMENCLATURE
    # --------------------------------------------------------

    def nomenclature_sections(self) -> Dict[str, Tuple[float, float]]:
        """{type: (largeur, hauteur)} lus dans les lignes de nomenclature du
        type « Poutre BA | 30x40 » (sections en cm)."""
        if self._sections is not None:
            return self._sections
        sections: Dict[str, Tuple[float, float]] = {}
        for text in self.placed_texts():
            match = SECTION_PATTERN.match(text.text)
            if not match:
                continue
            row = " ".join(normalize_text(t.text) for t in self.same_row(text))
            for keyword, type_code in NOMENCLATURE_KEYWORDS:
                if keyword in row:
                    sections.setdefault(type_code, (int(match.group(1)) / 100.0,
                                                    int(match.group(2)) / 100.0))
                    break
        self._sections = sections
        if sections:
            logger.info("Nomenclature : %s", sections)
        return sections

    def _nomenclature_slab_thickness(self) -> Optional[float]:
        for text in self.placed_texts():
            if not THICKNESS_PATTERN.search(text.text):
                continue
            row = " ".join(normalize_text(t.text) for t in self.same_row(text) + [text])
            if any(k in row for k in SLAB_KEYWORDS):
                return self._thickness(text.text)
        return None

    # --------------------------------------------------------
    # REPÈRES
    # --------------------------------------------------------

    @staticmethod
    def _clean_label(text: str) -> str:
        return re.sub(r"\s+", "", text.strip().upper())

    def _label(self, items: List[DetectedFormwork], type_code: str) -> None:
        """Rattache à chaque ouvrage le repère le plus proche, chaque repère
        servant une seule fois : deux poteaux voisins ne se disputent pas le
        même « P01 ». Sans repère, la clé dérive de la position (stable
        d'une analyse à l'autre)."""
        pattern = LABEL_PATTERNS.get(type_code)
        pending = [i for i in items if not i.key]
        if pattern:
            labels = [(self._clean_label(m.group(1)), t.x, t.y)
                      for t in self.placed_texts()
                      for m in [pattern.match(t.text)] if m]
            limit = MAX_LABEL_DISTANCE / self.unit_scale
            candidates = sorted(
                (math.hypot(x - i.center_x, y - i.center_y), n, k)
                for n, i in enumerate(pending) for k, (_l, x, y) in enumerate(labels))
            used_items, used_labels = set(), set()
            for distance, n, k in candidates:
                if distance > limit:
                    break
                if n in used_items or k in used_labels:
                    continue
                used_items.add(n)
                used_labels.add(k)
                pending[n].key = labels[k][0]
                pending[n].label_found = True
                pending[n].confidence += 0.15

        for item in items:
            if not item.key:
                item.key = "%s_x%d_y%d" % (
                    KEY_PREFIXES[type_code],
                    round(item.center_x * self.unit_scale * 100),
                    round(item.center_y * self.unit_scale * 100))
                if pattern:
                    item.issues.insert(0, "Repère généré depuis la position "
                                          "(aucun texte de repérage à proximité)")

    # --------------------------------------------------------
    # DÉDUPLICATION
    # --------------------------------------------------------

    def _deduplicate(self, items: List[DetectedFormwork]) -> List[DetectedFormwork]:
        kept: List[DetectedFormwork] = []
        tolerance = DEDUP_TOLERANCE / self.unit_scale
        for item in sorted(items, key=lambda i: -i.confidence):
            if not any(o.type_code == item.type_code
                       and abs(o.center_x - item.center_x) < tolerance
                       and abs(o.center_y - item.center_y) < tolerance
                       and abs(o.dimensions.get("l", 0) - item.dimensions.get("l", 0)) < DEDUP_TOLERANCE
                       for o in kept):
                kept.append(item)

        seen: Dict[str, int] = {}
        for item in kept:
            count = seen.get(item.key, 0)
            seen[item.key] = count + 1
            if count:
                item.key = "%s-%d" % (item.key, count + 1)
                item.confidence = max(item.confidence - 0.1, 0.0)
        return sorted(kept, key=lambda i: (i.type_code, i.key))

    def export_json(self, items: List[DetectedFormwork], output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.to_analysis_result(items), f, ensure_ascii=False, indent=2)


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Détection d'un plan de coffrage")
    parser.add_argument("dxf_path")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("-n", "--level", default=None)
    parser.add_argument("-s", "--scale", type=float, default=1.0)
    args = parser.parse_args()

    service = FormworkDetectionService(
        args.dxf_path, PlanContext.build(view="plan", level=args.level,
                                         level_label=args.level),
        unit_scale=args.scale)
    detected = service.detect()
    if args.output:
        service.export_json(detected, args.output)
    for d in detected:
        dims = " ".join("%s=%.2f" % kv for kv in d.dimensions.items()
                        if isinstance(kv[1], (int, float)))
        qty = " ".join("%s=%.2f" % kv for kv in d.quantities.items())
        print(f"{d.type_code:8s} {d.key:16s} {dims:42s} {qty:45s} conf={d.confidence:.2f}")
