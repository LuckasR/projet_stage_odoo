# -*- coding: utf-8 -*-
"""
facade_detection_service.py
============================

Lecture complète d'un plan de façade (vue en élévation) : ce que le dessin
montre du bâtiment vu de l'extérieur, façade par façade.

Un plan de façade porte presque toujours PLUSIEURS façades dans le même
fichier (Nord, Sud, Est, Ouest), chacune dessinée comme un contour fermé et
accompagnée d'un texte « FACADE NORD ». On détecte donc une façade par
contour, puis on rattache à chacune ce qui la concerne :

    Façade
      ├── Informations générales  orientation, n° du dessin, emprise
      ├── Niveaux                 bandes d'étage séparées par les dalles
      ├── Murs                    délégués à construction.wall (voir plus bas)
      ├── Ouvertures              portes, fenêtres, baies + allège / linteau
      ├── Éléments architecturaux balcon, garde-corps, corniche, toiture...
      ├── Cotes                   cotes horizontales, verticales, altimétriques
      └── Annotations             repères, matériaux, détails techniques

Ce que la vue de façade NE donne PAS : l'épaisseur des murs et la position
en plan des ouvrages. Ces valeurs ne sont jamais inventées — elles restent
vides jusqu'à l'import d'une vue en plan du même niveau.

Pourquoi les murs ne sont pas détectés ici
------------------------------------------
Le mur de façade est déjà produit par `wall_detection_service` (un mur par
étage et par bloc, cf. `_detect_from_elevation_view`) et vit dans
construction.wall, où il se complète d'une vue à l'autre. Ce service ne le
redétecte pas : il se contente de fournir l'emprise et les bandes d'étage
qui permettent au modèle de rattacher ces murs à la bonne façade.

Repère altimétrique
-------------------
Les hauteurs (allège, linteau, bandes d'étage) sont mesurées depuis le BAS
de la façade, pas depuis le zéro du dessin : c'est la seule référence
comparable d'un plan à l'autre, les dessinateurs ne plaçant pas tous leur
origine au même endroit.

Dépendances :
    pip install ezdxf shapely
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from .plan_analysis import (
        VIEW_ELEVATION, DxfPlanReader, Outline, PlanContext,
        find_orientation, normalize_text,
    )
except ImportError:  # exécution directe du module en ligne de commande
    from plan_analysis import (  # type: ignore[no-redef]
        VIEW_ELEVATION, DxfPlanReader, Outline, PlanContext,
        find_orientation, normalize_text,
    )

logger = logging.getLogger("facade_detection_service")
logging.basicConfig(level=logging.INFO)


# ============================================================
# CALQUES
# ============================================================

# Contour de la façade. Sur un vrai plan d'élévation le mur n'est pas
# redessiné sur les calques A-MUR-* : il est tracé sur un calque dédié à la
# vue. On cherche donc les deux familles, sans a priori sur celle que le
# bureau d'études a utilisée.
FACADE_OUTLINE_LAYERS = ("A-FAC-CONT", "A-MUR-EXT", "A-MUR-INT", "MURS_EXT", "MURS_INT")

# Détails de façade : dalles de plancher (qui séparent les étages),
# appuis, linteaux.
FACADE_DETAIL_LAYERS = ("A-FAC-DET",)

# Ouvertures : un calque par nature, c'est ce qui donne leur type.
OPENING_LAYERS: Dict[str, Tuple[str, ...]] = {
    "window": ("A-OUV-FEN", "A-FEN", "A-FENETRE"),
    "door": ("A-OUV-PRT", "A-PORTE", "A-PTE"),
    "french_window": ("A-PORTE-FEN", "A-PFEN"),
    "bay": ("A-BAIE",),
    "garage_door": ("A-PORTE-GAR", "A-PGAR"),
}

# Calques d'ouvertures qui ne disent pas leur nature : elle est alors déduite
# de la géométrie (une ouverture qui part du sol de l'étage est une porte).
GENERIC_OPENING_LAYERS: Tuple[str, ...] = (
    "OUVERTURES", "A-OUV", "A-OUVERTURE", "A-OUVERTURES", "A-MENUISERIE",
    "MENUISERIES")

# Éléments architecturaux : idem, le calque porte la nature de l'ouvrage.
FEATURE_LAYERS: Dict[str, Tuple[str, ...]] = {
    "balcony": ("A-BALCON", "A-BAL"),
    "terrace": ("A-TERRASSE", "A-TER"),
    "railing": ("A-GARDE-CORPS", "A-GC"),
    "cornice": ("A-CORNICHE", "A-CORN"),
    "roof": ("A-TOITURE", "A-TOIT"),
    "canopy": ("A-AUVENT", "A-AUV"),
    "stairs": ("A-ESCALIER", "A-ESC"),
    "shutter": ("A-VOLET",),
}

# Cotes et annotations : ces calques ne servent qu'à filtrer, la nature
# réelle est déduite du contenu (entité DIMENSION, texte altimétrique...).
DIMENSION_LAYERS = ("A-COTE", "A-COTES", "COTES", "COTATION")
ANNOTATION_LAYERS = ("A-TEXTE", "A-TXT", "A-ANNO", "A-REPERE", "TEXTE")


# ============================================================
# DIMENSIONS PLAUSIBLES (en mètres)
# ============================================================

MIN_FACADE_WIDTH = 2.00
MAX_FACADE_WIDTH = 120.00
MIN_FACADE_HEIGHT = 1.50
MAX_FACADE_HEIGHT = 60.00

MIN_OPENING_WIDTH = 0.30
MAX_OPENING_WIDTH = 8.00
MIN_OPENING_HEIGHT = 0.30
MAX_OPENING_HEIGHT = 5.00

MIN_FEATURE_SIZE = 0.10
MAX_FEATURE_SIZE = 40.00

# Une dalle traverse (presque) toute la largeur de la façade ; un linteau ou
# un appui de fenêtre ne fait que quelques dizaines de centimètres.
SLAB_MIN_LENGTH_RATIO = 0.5
SLAB_MIN_THICKNESS = 0.05
SLAB_MAX_THICKNESS = 0.50
SLAB_ANGLE_TOLERANCE = 10.0

# Sans dalle dessinée, les étages sont découpés aux niveaux altimétriques
# (« +3.00 ») ; une bande plus basse que ça n'est pas un étage.
MIN_FLOOR_HEIGHT = 1.50

# Une ouverture dont le bas est à moins de ça du sol de l'étage part du sol :
# c'est une porte (ou une porte-fenêtre), pas une fenêtre.
FLOOR_SILL_TOLERANCE = 0.15

# Distance max entre un texte et l'ouvrage qu'il désigne.
LABEL_MAX_DISTANCE = 2.00
# Distance max entre une façade et une cote / un texte qui s'y rapporte :
# les cotes sont dessinées EN DEHORS du contour, le long de ses bords.
CONTEXT_MAX_DISTANCE = 10.00

# Deux ouvrages dont les coins sont plus proches que ça et de mêmes
# dimensions sont le même ouvrage dessiné deux fois.
DEDUP_TOLERANCE = 0.05

# Tolérance angulaire pour juger une cote horizontale ou verticale.
DIMENSION_ANGLE_TOLERANCE = 5.0

# Marge de débordement admise autour du contour d'une façade : un balcon ou
# une corniche dépassent légitimement du nu du mur.
CONTAINMENT_PAD = 1.00


# ============================================================
# MOTIFS DE TEXTE
# ============================================================

# Repère d'ouverture : F1, FEN-2, P3, PORTE 4, B5, PF1...
OPENING_LABEL_PATTERN = re.compile(
    r"^\s*(PF|FEN|PORTE|BAIE|F|P|B)[\s\-_]?\d+[A-Za-z]?\s*$", re.IGNORECASE)

# Niveau altimétrique : +3.00, ± 0.00, -1.50, NIV +6.00. Le signe est exigé :
# un « 3.00 » nu est une cote, pas une altitude.
ALTIMETRIC_PATTERN = re.compile(
    r"^\s*(?:niv\.?|n\.?g\.?f\.?)?\s*([±+\-])\s*(\d{1,2})[.,](\d{1,2})\s*$",
    re.IGNORECASE)

# Numéro du dessin dans le cartouche : « N° A-04 », « PLAN No 12 ».
# Le « o » de l'abréviation doit finir un mot, sinon le « NO » de « FACADE
# NORD » est lu comme un numéro de dessin.
DRAWING_NUMBER_PATTERN = re.compile(
    r"\bn\s*(?:[°º]|o\.|o\b)\s*[:\-]?\s*([a-z0-9][a-z0-9\-/\.]{0,19})",
    re.IGNORECASE)

# Matériaux cités en annotation. Clés sans accent : la comparaison se fait
# sur du texte normalisé (cf. plan_analysis.normalize_text).
MATERIAL_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "concrete": ("beton", "b.a", "banche"),
    "brick": ("brique",),
    "block": ("parpaing", "agglo", "bloc creux"),
    "stone": ("pierre", "moellon"),
    "wood": ("bois",),
    "metal": ("acier", "alu", "aluminium", "metal", "metallique"),
    "pvc": ("pvc",),
    "glass": ("verre", "vitrage", "vitre"),
    "render": ("enduit", "crepi", "platre"),
}

# Vocabulaire des détails techniques : ces textes ne sont ni un repère, ni
# une altitude, ni un simple nom de matériau.
TECHNICAL_KEYWORDS = (
    "ep.", "ep ", "epaisseur", "detail", "coupe", "voir", "cf.", "acrotere",
    "chainage", "linteau", "allege", "seuil", "appui", "isolation", "joint",
)


# ============================================================
# STRUCTURES DE DONNÉES — MIROIR DES MODÈLES ODOO
# ============================================================

@dataclass
class DetectedFacadeLevel:
    """Bande d'étage de la façade, entre deux dalles."""

    floor_index: int
    bottom_elevation: float
    top_elevation: float
    slab_thickness: float = 0.0

    @property
    def height(self) -> float:
        return self.top_elevation - self.bottom_elevation

    def to_odoo_vals(self) -> dict:
        return {
            "floor_index": self.floor_index,
            "sequence": self.floor_index * 10,
            "bottom_elevation": round(self.bottom_elevation, 3),
            "top_elevation": round(self.top_elevation, 3),
            "slab_thickness": round(self.slab_thickness, 3),
        }


@dataclass
class DetectedOpening:
    """Porte, fenêtre ou baie relevée sur la façade. Les hauteurs d'allège et
    de linteau sont comptées depuis le bas de la façade."""

    opening_type: str
    width: float
    height: float
    sill_height: float
    lintel_height: float
    pos_x: float
    pos_y: float
    center_x: float
    center_y: float
    layer: Optional[str] = None
    mark: Optional[str] = None
    floor_index: Optional[int] = None
    confidence: float = 75.0

    def to_odoo_vals(self) -> dict:
        return {
            "name": self.mark or self.default_name,
            "mark": self.mark or False,
            "opening_type": self.opening_type,
            "width": round(self.width, 3),
            "height": round(self.height, 3),
            "sill_height": round(self.sill_height, 3),
            "lintel_height": round(self.lintel_height, 3),
            "pos_x": round(self.pos_x, 3),
            "pos_y": round(self.pos_y, 3),
            "center_x": round(self.center_x, 3),
            "center_y": round(self.center_y, 3),
            "layer": self.layer or False,
            "confidence": round(self.confidence, 2),
        }

    @property
    def default_name(self) -> str:
        return "%s %.2f x %.2f m" % (self.opening_type, self.width, self.height)


@dataclass
class DetectedFeature:
    """Ouvrage architectural visible en façade (balcon, corniche, toiture...)."""

    feature_type: str
    width: float
    height: float
    pos_x: float
    pos_y: float
    center_x: float
    center_y: float
    layer: Optional[str] = None
    floor_index: Optional[int] = None
    confidence: float = 70.0

    def to_odoo_vals(self) -> dict:
        return {
            "name": "%s %.2f x %.2f m" % (self.feature_type, self.width, self.height),
            "feature_type": self.feature_type,
            "width": round(self.width, 3),
            "height": round(self.height, 3),
            "pos_x": round(self.pos_x, 3),
            "pos_y": round(self.pos_y, 3),
            "center_x": round(self.center_x, 3),
            "center_y": round(self.center_y, 3),
            "layer": self.layer or False,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class DetectedDimension:
    """Cote portée au dessin. `value` est la mesure lue (mètres) ;
    `elevation` n'est renseignée que pour les niveaux altimétriques."""

    dimension_type: str
    value: float = 0.0
    elevation: float = 0.0
    text: Optional[str] = None
    pos_x: float = 0.0
    pos_y: float = 0.0
    layer: Optional[str] = None
    origin: str = "dimension"

    def to_odoo_vals(self) -> dict:
        return {
            "name": self.text or ("%.2f m" % self.value),
            "dimension_type": self.dimension_type,
            "value": round(self.value, 3),
            "elevation": round(self.elevation, 3),
            "text": self.text or False,
            "pos_x": round(self.pos_x, 3),
            "pos_y": round(self.pos_y, 3),
            "layer": self.layer or False,
            "origin": self.origin,
        }


@dataclass
class DetectedAnnotation:
    """Texte du dessin, classé par ce qu'il apporte."""

    text: str
    annotation_type: str
    pos_x: float = 0.0
    pos_y: float = 0.0
    layer: Optional[str] = None
    material: Optional[str] = None

    def to_odoo_vals(self) -> dict:
        return {
            "name": self.text[:120],
            "text": self.text,
            "annotation_type": self.annotation_type,
            "material": self.material or False,
            "pos_x": round(self.pos_x, 3),
            "pos_y": round(self.pos_y, 3),
            "layer": self.layer or False,
        }


@dataclass
class DetectedFacade:
    """Une façade et tout ce que le plan en dit."""

    name: str
    match_key: str
    orientation: Optional[str] = None
    drawing_number: Optional[str] = None
    layer: Optional[str] = None
    width: float = 0.0
    height: float = 0.0
    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 0.0
    max_y: float = 0.0
    material: Optional[str] = None
    confidence: float = 70.0
    detection_method: str = "geometry"
    levels: List[DetectedFacadeLevel] = field(default_factory=list)
    openings: List[DetectedOpening] = field(default_factory=list)
    features: List[DetectedFeature] = field(default_factory=list)
    dimensions: List[DetectedDimension] = field(default_factory=list)
    annotations: List[DetectedAnnotation] = field(default_factory=list)

    def to_odoo_vals(self) -> dict:
        """Champs scalaires de construction.facade. Les enfants sont écrits
        par le modèle, qui seul sait résoudre les niveaux."""
        return {
            "name": self.name,
            "match_key": self.match_key,
            "orientation": self.orientation or False,
            "drawing_number": self.drawing_number or False,
            "layer": self.layer or False,
            "width": round(self.width, 3),
            "height": round(self.height, 3),
            "min_x": round(self.min_x, 3),
            "min_y": round(self.min_y, 3),
            "max_x": round(self.max_x, 3),
            "max_y": round(self.max_y, 3),
            "material": self.material or False,
            "confidence": round(self.confidence, 2),
            "detection_method": self.detection_method,
        }

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# SERVICE
# ============================================================

class FacadeDetectionService(DxfPlanReader):
    """Lit un DXF classé en vue « Façade » et en extrait les façades
    dessinées, avec leurs ouvertures, ouvrages, cotes et annotations.

    Toutes les longueurs renvoyées sont en mètres : `unit_scale` donne le
    nombre de mètres par unité de dessin (0.001 pour un DXF en millimètres),
    relevé à l'import depuis $INSUNITS."""

    def __init__(self, dxf_path: str, context: Optional[PlanContext] = None,
                 unit_scale: float = 1.0):
        super().__init__(dxf_path)
        self.context = context or PlanContext()
        self.unit_scale = unit_scale or 1.0
        self._layer_index = self._build_layer_index()

    # --------------------------------------------------------
    # CALQUES : correspondance tolérante
    # --------------------------------------------------------

    def _build_layer_index(self) -> Dict[str, str]:
        """Calques réellement présents, indexés par leur nom normalisé.

        La casse et les accents varient d'un bureau d'études à l'autre
        (« A-Fen », « a-fenetre ») : chercher le nom exact ferait manquer
        des ouvrages pour une simple majuscule."""
        index: Dict[str, str] = {}
        try:
            for layer in self.doc.layers:
                index[normalize_text(layer.dxf.name)] = layer.dxf.name
        except Exception as exc:
            logger.debug("Lecture de la table des calques impossible : %s", exc)
        return index

    def _layers(self, wanted: Sequence[str]) -> List[str]:
        """Noms réels des calques du dessin correspondant aux noms attendus."""
        found = []
        for name in wanted:
            real = self._layer_index.get(normalize_text(name))
            if real and real not in found:
                found.append(real)
        return found

    def _scale(self, value: float) -> float:
        return value * self.unit_scale

    # --------------------------------------------------------
    # POINT D'ENTRÉE
    # --------------------------------------------------------

    def detect_facades(self) -> List[DetectedFacade]:
        ctx = self.context
        if ctx.view != VIEW_ELEVATION:
            logger.info("La vue « %s » n'est pas une façade : aucune détection",
                        ctx.view)
            return []

        facades = self._detect_facade_blocks()
        if not facades:
            logger.warning("Aucune façade exploitable dans %s", self.dxf_path)
            return []

        drawing_number = self._find_drawing_number()
        for facade in facades:
            facade.drawing_number = drawing_number

        self._attach_levels(facades)
        self._attach_openings(facades)
        self._attach_features(facades)
        self._attach_dimensions(facades)
        self._attach_annotations(facades)
        self._infer_materials(facades)

        for facade in facades:
            logger.info(
                "Façade %s : %.2f x %.2f m, %d niveau(x), %d ouverture(s), "
                "%d ouvrage(s), %d cote(s), %d annotation(s)",
                facade.name, facade.width, facade.height, len(facade.levels),
                len(facade.openings), len(facade.features),
                len(facade.dimensions), len(facade.annotations))
        return facades

    # --------------------------------------------------------
    # EMPRISE DES FAÇADES
    # --------------------------------------------------------

    def _detect_facade_blocks(self) -> List[DetectedFacade]:
        outlines = [
            o for o in self.collect_closed_outlines(self._layers(FACADE_OUTLINE_LAYERS))
            if self._is_plausible_facade(o)
        ]
        if not outlines:
            return self._detect_facade_fallback()

        label_texts = [
            (text, x, y) for text, x, y in self.collect_texts_with_position()
            if find_orientation(text)
        ]
        single = len(outlines) == 1
        facades: List[DetectedFacade] = []

        for index, outline in enumerate(outlines):
            orientation = self._nearest_orientation(outline, label_texts)
            if not orientation and single:
                orientation = find_orientation(self.context.title)
            facades.append(self._build_facade(outline, orientation, index,
                                              confidence=85.0 if orientation else 70.0))
        return facades

    def _detect_facade_fallback(self) -> List[DetectedFacade]:
        """Plan dessiné en traits ouverts : pas de contour fermé exploitable.
        On retombe sur l'emprise globale, une seule façade et sans découpe."""
        segments = self.collect_segments(self._layers(FACADE_OUTLINE_LAYERS))
        box = self.segments_bounding_box(segments)
        if not box:
            return []

        minx, miny, maxx, maxy = box
        outline = Outline(minx=minx, miny=miny, maxx=maxx, maxy=maxy,
                          layer=segments[0][1] if segments else "",
                          points=[(minx, miny), (maxx, maxy)])
        if not self._is_plausible_facade(outline):
            logger.warning("Emprise implausible (%.2f x %.2f m) dans %s : ignorée",
                           self._scale(outline.width), self._scale(outline.height),
                           self.dxf_path)
            return []

        orientation = find_orientation(self.context.title, *self.collect_texts())
        return [self._build_facade(outline, orientation, 0,
                                   confidence=60.0 if orientation else 50.0)]

    def _is_plausible_facade(self, outline: Outline) -> bool:
        width = self._scale(outline.width)
        height = self._scale(outline.height)
        return (MIN_FACADE_WIDTH <= width <= MAX_FACADE_WIDTH
                and MIN_FACADE_HEIGHT <= height <= MAX_FACADE_HEIGHT)

    def _build_facade(self, outline: Outline, orientation: Optional[str],
                      index: int, confidence: float) -> DetectedFacade:
        label = orientation or "sans-orientation"
        # Sans orientation, deux façades du même plan auraient la même clé :
        # leur rang dans le dessin les distingue en attendant une correction.
        suffix = label if orientation else "%s-%d" % (label, index)
        return DetectedFacade(
            name="Façade %s" % label,
            match_key=self.context.match_key("facade-%s" % suffix),
            orientation=orientation,
            layer=outline.layer,
            width=self._scale(outline.width),
            height=self._scale(outline.height),
            min_x=self._scale(outline.minx),
            min_y=self._scale(outline.miny),
            max_x=self._scale(outline.maxx),
            max_y=self._scale(outline.maxy),
            confidence=confidence,
        )

    def _nearest_orientation(self, outline: Outline,
                             label_texts: List[Tuple[str, float, float]]
                             ) -> Optional[str]:
        """Orientation portée par le texte « FACADE NORD » le plus proche du
        centre du contour. Un texte trop loin appartient à une autre façade."""
        if not label_texts:
            return None
        cx, cy = outline.center
        best_text, best_distance = None, CONTEXT_MAX_DISTANCE / self.unit_scale
        for text, x, y in label_texts:
            distance = math.hypot(x - cx, y - cy)
            if distance < best_distance:
                best_text, best_distance = text, distance
        return find_orientation(best_text) if best_text else None

    def _find_drawing_number(self) -> Optional[str]:
        """Un numéro de dessin porte toujours un chiffre : cette exigence
        écarte les faux positifs du cartouche (« N° DE PLAN », « No REV »)."""
        for text in self.collect_texts():
            match = DRAWING_NUMBER_PATTERN.search(text or "")
            if match:
                number = match.group(1).strip().upper()
                if any(char.isdigit() for char in number):
                    return number
        return None

    # --------------------------------------------------------
    # RATTACHEMENT D'UN POINT À UNE FAÇADE
    # --------------------------------------------------------

    @staticmethod
    def _contains(facade: DetectedFacade, minx: float, miny: float,
                  maxx: float, maxy: float, pad: float = 0.0) -> bool:
        return (facade.min_x - pad <= minx and maxx <= facade.max_x + pad
                and facade.min_y - pad <= miny and maxy <= facade.max_y + pad)

    @staticmethod
    def _box_distance(facade: DetectedFacade, x: float, y: float) -> float:
        dx = max(facade.min_x - x, 0.0, x - facade.max_x)
        dy = max(facade.min_y - y, 0.0, y - facade.max_y)
        return math.hypot(dx, dy)

    def _owner_of(self, facades: List[DetectedFacade], minx: float, miny: float,
                  maxx: float, maxy: float) -> Optional[DetectedFacade]:
        """Façade qui contient l'ouvrage. Le débord admis laisse passer un
        balcon ou une corniche qui dépasse du nu du mur."""
        for facade in facades:
            if self._contains(facade, minx, miny, maxx, maxy, CONTAINMENT_PAD):
                return facade
        return None

    def _closest_of(self, facades: List[DetectedFacade],
                    x: float, y: float) -> Optional[DetectedFacade]:
        """Façade la plus proche d'un point : les cotes et les textes sont
        dessinés EN DEHORS du contour, le long de ses bords."""
        best, best_distance = None, CONTEXT_MAX_DISTANCE
        for facade in facades:
            distance = self._box_distance(facade, x, y)
            if distance < best_distance:
                best, best_distance = facade, distance
        return best

    @staticmethod
    def _floor_index_at(facade: DetectedFacade, y: float) -> Optional[int]:
        for level in facade.levels:
            bottom = facade.min_y + level.bottom_elevation
            top = facade.min_y + level.top_elevation
            if bottom <= y <= top:
                return level.floor_index
        return None

    # --------------------------------------------------------
    # NIVEAUX : BANDES D'ÉTAGE SÉPARÉES PAR LES DALLES
    # --------------------------------------------------------

    def _attach_levels(self, facades: List[DetectedFacade]) -> None:
        altimetric = self._collect_altimetric_texts()
        for facade in facades:
            slabs = self._find_slabs(facade) or self._altimetric_floor_lines(
                facade, facades, altimetric)
            bands: List[DetectedFacadeLevel] = []
            previous_top = facade.min_y
            for index, (slab_bottom, slab_top) in enumerate(slabs):
                bands.append(DetectedFacadeLevel(
                    floor_index=index,
                    bottom_elevation=previous_top - facade.min_y,
                    top_elevation=slab_bottom - facade.min_y,
                    slab_thickness=slab_top - slab_bottom,
                ))
                previous_top = slab_top
            bands.append(DetectedFacadeLevel(
                floor_index=len(bands),
                bottom_elevation=previous_top - facade.min_y,
                top_elevation=facade.max_y - facade.min_y,
            ))
            facade.levels = [b for b in bands if b.height > 0]

    def _altimetric_floor_lines(self, facade: DetectedFacade,
                                facades: List[DetectedFacade],
                                altimetric) -> List[Tuple[float, float]]:
        """Planchers lus dans les niveaux altimétriques de la façade, quand
        aucune dalle n'est dessinée : « +3.00 » au-dessus du « ±0.00 » est un
        plancher. Renvoyés comme des dalles d'épaisseur nulle.

        Les altitudes sont lues dans le TEXTE, pas dans sa position : le
        repère le plus bas sert d'origine, et c'est l'écart d'altitude qui
        place les autres — un texte décalé de quelques centimètres au-dessus
        de son trait ne déplace donc pas le plancher."""
        own = [(d.elevation, y) for d, x, y in altimetric
               if self._closest_of(facades, x, y) is facade]
        if len(own) < 2:
            # Façades dessinées côte à côte : les niveaux ne sont souvent cotés
            # que sur l'une d'elles. On reprend ceux qui sont à sa hauteur.
            own = [(d.elevation, y) for d, x, y in altimetric
                   if self._box_distance(facade, x, y) < CONTEXT_MAX_DISTANCE
                   and facade.min_y - LABEL_MAX_DISTANCE <= y
                   <= facade.max_y + LABEL_MAX_DISTANCE]
        if len(own) < 2:
            return []
        reference_elevation, reference_y = min(own)
        floors = set()
        for elevation, _y in own:
            y = reference_y + (elevation - reference_elevation)
            if (facade.min_y + MIN_FLOOR_HEIGHT <= y
                    <= facade.max_y - MIN_FLOOR_HEIGHT):
                floors.add(round(y, 3))
        return [(y, y) for y in sorted(floors)]

    def _find_slabs(self, facade: DetectedFacade) -> List[Tuple[float, float]]:
        """Dalles de plancher à l'intérieur de la façade : deux traits
        horizontaux parallèles traversant presque toute sa largeur. Un linteau
        est bien plus court — c'est ce qui les distingue, bien plus que leur
        épaisseur."""
        layers = self._layers(FACADE_DETAIL_LAYERS)
        if not layers:
            return []

        pad = 0.5 / self.unit_scale
        raw_segments = [
            (line, layer) for line, layer in self.collect_segments(layers)
            if self._segment_within(line, facade, pad)
        ]
        if not raw_segments:
            return []

        pairs = self.find_parallel_pairs(
            raw_segments,
            min_width=SLAB_MIN_THICKNESS / self.unit_scale,
            max_width=SLAB_MAX_THICKNESS / self.unit_scale,
            min_length=(facade.width * SLAB_MIN_LENGTH_RATIO) / self.unit_scale,
            angle_tolerance=SLAB_ANGLE_TOLERANCE,
        )

        slabs = []
        for pair in pairs:
            angle = self.line_angle(pair.axis)
            if not (angle <= SLAB_ANGLE_TOLERANCE
                    or angle >= 180 - SLAB_ANGLE_TOLERANCE):
                continue  # une dalle est horizontale ; on écarte les refends
            _, cy = pair.center
            center = self._scale(cy)
            half = self._scale(pair.width) / 2.0
            if facade.min_y < center < facade.max_y:
                slabs.append((center - half, center + half))
        return sorted(slabs)

    def _segment_within(self, line, facade: DetectedFacade, pad: float) -> bool:
        xs = [c[0] for c in line.coords]
        ys = [c[1] for c in line.coords]
        return self._contains(facade,
                              self._scale(min(xs)), self._scale(min(ys)),
                              self._scale(max(xs)), self._scale(max(ys)),
                              self._scale(pad))

    # --------------------------------------------------------
    # OUVERTURES
    # --------------------------------------------------------

    def _attach_openings(self, facades: List[DetectedFacade]) -> None:
        marks = [
            (text.strip(), self._scale(x), self._scale(y))
            for text, x, y in self.collect_texts_with_position()
            if OPENING_LABEL_PATTERN.match(text or "")
        ]

        groups = list(OPENING_LAYERS.items()) + [(None, GENERIC_OPENING_LAYERS)]
        for layer_type, layer_names in groups:
            layers = self._layers(layer_names)
            if not layers:
                continue
            for outline in self.collect_closed_outlines(layers):
                width = self._scale(outline.width)
                height = self._scale(outline.height)
                if not (MIN_OPENING_WIDTH <= width <= MAX_OPENING_WIDTH
                        and MIN_OPENING_HEIGHT <= height <= MAX_OPENING_HEIGHT):
                    logger.debug("Ouverture implausible (%.2f x %.2f m) sur %s",
                                 width, height, outline.layer)
                    continue

                minx, miny = self._scale(outline.minx), self._scale(outline.miny)
                maxx, maxy = self._scale(outline.maxx), self._scale(outline.maxy)
                facade = self._owner_of(facades, minx, miny, maxx, maxy)
                if not facade:
                    logger.debug("Ouverture hors de toute façade, ignorée (%s)",
                                 outline.layer)
                    continue

                cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
                floor_index = self._floor_index_at(facade, cy)
                opening_type = layer_type or self._infer_opening_type(
                    facade, floor_index, miny)
                opening = DetectedOpening(
                    opening_type=opening_type,
                    width=width,
                    height=height,
                    sill_height=miny - facade.min_y,
                    lintel_height=maxy - facade.min_y,
                    pos_x=minx, pos_y=miny,
                    center_x=cx, center_y=cy,
                    layer=outline.layer,
                    mark=self._nearest_mark(marks, cx, cy),
                    floor_index=floor_index,
                )
                if opening.mark:
                    opening.confidence = 90.0
                facade.openings.append(opening)

        for facade in facades:
            facade.openings = self._deduplicate(facade.openings)

    @staticmethod
    def _infer_opening_type(facade: DetectedFacade, floor_index: Optional[int],
                            bottom: float) -> str:
        """Nature d'une ouverture tracée sur un calque générique : elle part
        du sol de son étage -> porte, sinon fenêtre."""
        floor = next((level for level in facade.levels
                      if level.floor_index == floor_index), None)
        floor_y = facade.min_y + (floor.bottom_elevation if floor else 0.0)
        return "door" if bottom - floor_y <= FLOOR_SILL_TOLERANCE else "window"

    @staticmethod
    def _nearest_mark(marks: List[Tuple[str, float, float]],
                      cx: float, cy: float) -> Optional[str]:
        best, best_distance = None, LABEL_MAX_DISTANCE
        for text, x, y in marks:
            distance = math.hypot(x - cx, y - cy)
            if distance < best_distance:
                best, best_distance = text, distance
        return best.upper() if best else None

    @staticmethod
    def _deduplicate(items):
        """Même ouvrage dessiné deux fois (contour + hachure, calque doublé)."""
        kept = []
        for item in items:
            duplicate = any(
                abs(item.center_x - other.center_x) < DEDUP_TOLERANCE
                and abs(item.center_y - other.center_y) < DEDUP_TOLERANCE
                and abs(item.width - other.width) < DEDUP_TOLERANCE
                and abs(item.height - other.height) < DEDUP_TOLERANCE
                for other in kept
            )
            if not duplicate:
                kept.append(item)
        return kept

    # --------------------------------------------------------
    # ÉLÉMENTS ARCHITECTURAUX
    # --------------------------------------------------------

    def _attach_features(self, facades: List[DetectedFacade]) -> None:
        for feature_type, layer_names in FEATURE_LAYERS.items():
            layers = self._layers(layer_names)
            if not layers:
                continue

            outlines = self.collect_closed_outlines(layers)
            if outlines:
                for outline in outlines:
                    self._add_feature(facades, feature_type, outline.layer,
                                      self._scale(outline.minx), self._scale(outline.miny),
                                      self._scale(outline.maxx), self._scale(outline.maxy),
                                      confidence=75.0)
                continue

            # Ouvrage dessiné en traits ouverts (garde-corps, corniche) :
            # son emprise sur le calque en tient lieu.
            box = self.segments_bounding_box(self.collect_segments(layers))
            if box:
                self._add_feature(facades, feature_type, layers[0],
                                  self._scale(box[0]), self._scale(box[1]),
                                  self._scale(box[2]), self._scale(box[3]),
                                  confidence=60.0)

        for facade in facades:
            facade.features = self._deduplicate(facade.features)

    def _add_feature(self, facades: List[DetectedFacade], feature_type: str,
                     layer: str, minx: float, miny: float, maxx: float,
                     maxy: float, confidence: float) -> None:
        width, height = maxx - minx, maxy - miny
        if not (MIN_FEATURE_SIZE <= max(width, height) <= MAX_FEATURE_SIZE):
            logger.debug("Ouvrage %s implausible (%.2f x %.2f m) : ignoré",
                         feature_type, width, height)
            return

        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        facade = (self._owner_of(facades, minx, miny, maxx, maxy)
                  or self._closest_of(facades, cx, cy))
        if not facade:
            return

        facade.features.append(DetectedFeature(
            feature_type=feature_type,
            width=width, height=height,
            pos_x=minx, pos_y=miny,
            center_x=cx, center_y=cy,
            layer=layer,
            floor_index=self._floor_index_at(facade, cy),
            confidence=confidence,
        ))

    # --------------------------------------------------------
    # COTES
    # --------------------------------------------------------

    def _attach_dimensions(self, facades: List[DetectedFacade]) -> None:
        for detected, x, y in self._collect_dimension_entities():
            facade = self._closest_of(facades, x, y)
            if facade:
                facade.dimensions.append(detected)

        for detected, x, y in self._collect_altimetric_texts():
            facade = self._closest_of(facades, x, y)
            if facade:
                facade.dimensions.append(detected)

    def _collect_dimension_entities(self
                                    ) -> List[Tuple[DetectedDimension, float, float]]:
        """Entités DIMENSION du dessin : c'est la cotation « vraie », celle qui
        porte sa mesure. Un dessinateur qui cote à la main laisse un simple
        texte — repris par `_collect_altimetric_texts` pour les altitudes."""
        found: List[Tuple[DetectedDimension, float, float]] = []
        try:
            entities = list(self.msp.query("DIMENSION"))
        except Exception as exc:
            logger.debug("Lecture des cotes impossible : %s", exc)
            return found

        for entity in entities:
            try:
                measurement = float(entity.get_measurement())
            except Exception:
                measurement = 0.0
            position = (entity.dxf.get("text_midpoint", None)
                        or entity.dxf.get("defpoint", None))
            if position is None:
                continue
            x, y = self._scale(position.x), self._scale(position.y)

            raw_text = entity.dxf.get("text", "") or ""
            found.append((
                DetectedDimension(
                    dimension_type=self._dimension_orientation(entity),
                    value=abs(self._scale(measurement)),
                    text=raw_text if raw_text not in ("", "<>") else None,
                    pos_x=x, pos_y=y,
                    layer=entity.dxf.get("layer", None),
                    origin="dimension",
                ), x, y))
        return found

    def _dimension_orientation(self, entity) -> str:
        """Une cote linéaire est soit « tournée » (son angle est porté par
        `angle`), soit « alignée » sur deux points de référence."""
        angle = None
        try:
            dimtype = int(entity.dxf.get("dimtype", 0)) & 7
        except Exception:
            dimtype = 0

        if dimtype == 0:
            angle = entity.dxf.get("angle", 0.0)
        else:
            start = entity.dxf.get("defpoint2", None)
            end = entity.dxf.get("defpoint3", None)
            if start is not None and end is not None:
                angle = math.degrees(math.atan2(end.y - start.y, end.x - start.x))

        if angle is None:
            return "other"
        normalized = abs(float(angle)) % 180
        if (normalized <= DIMENSION_ANGLE_TOLERANCE
                or normalized >= 180 - DIMENSION_ANGLE_TOLERANCE):
            return "horizontal"
        if abs(normalized - 90) <= DIMENSION_ANGLE_TOLERANCE:
            return "vertical"
        return "other"

    def _collect_altimetric_texts(self
                                  ) -> List[Tuple[DetectedDimension, float, float]]:
        """Niveaux altimétriques (« +3.00 », « ± 0.00 ») : ce sont des textes,
        jamais des entités DIMENSION."""
        found: List[Tuple[DetectedDimension, float, float]] = []
        for text, raw_x, raw_y in self.collect_texts_with_position():
            elevation = self._parse_elevation(text)
            if elevation is None:
                continue
            x, y = self._scale(raw_x), self._scale(raw_y)
            found.append((
                DetectedDimension(
                    dimension_type="altimetric",
                    elevation=elevation,
                    text=text.strip(),
                    pos_x=x, pos_y=y,
                    origin="text",
                ), x, y))
        return found

    @staticmethod
    def _parse_elevation(text: Optional[str]) -> Optional[float]:
        match = ALTIMETRIC_PATTERN.match(text or "")
        if not match:
            return None
        sign, whole, decimals = match.groups()
        value = float("%s.%s" % (whole, decimals))
        return -value if sign == "-" else value

    # --------------------------------------------------------
    # ANNOTATIONS
    # --------------------------------------------------------

    def _attach_annotations(self, facades: List[DetectedFacade]) -> None:
        for text, raw_x, raw_y in self.collect_texts_with_position():
            content = (text or "").strip()
            if not content:
                continue
            x, y = self._scale(raw_x), self._scale(raw_y)
            facade = self._closest_of(facades, x, y)
            if not facade:
                continue

            annotation_type, material = self._classify_annotation(content)
            facade.annotations.append(DetectedAnnotation(
                text=content,
                annotation_type=annotation_type,
                material=material,
                pos_x=x, pos_y=y,
            ))

    @classmethod
    def _classify_annotation(cls, text: str) -> Tuple[str, Optional[str]]:
        if cls._parse_elevation(text) is not None:
            return "level", None
        if OPENING_LABEL_PATTERN.match(text):
            return "mark", None

        normalized = normalize_text(text)
        material = cls._find_material(normalized)
        if material:
            return "material", material
        if any(keyword in normalized for keyword in TECHNICAL_KEYWORDS):
            return "technical", None
        return "general", None

    @staticmethod
    def _find_material(normalized_text: str) -> Optional[str]:
        for material, keywords in MATERIAL_KEYWORDS.items():
            if any(keyword in normalized_text for keyword in keywords):
                return material
        return None

    def _infer_materials(self, facades: List[DetectedFacade]) -> None:
        """Matériau principal de la façade : celui que ses annotations citent
        le plus souvent. Sans annotation, il reste inconnu — la façade ne
        permet pas de le deviner."""
        for facade in facades:
            counts: Dict[str, int] = {}
            for annotation in facade.annotations:
                if annotation.material:
                    counts[annotation.material] = counts.get(annotation.material, 0) + 1
            if counts:
                facade.material = max(counts, key=counts.get)

    # --------------------------------------------------------
    # EXPORT
    # --------------------------------------------------------

    def export_json(self, facades: List[DetectedFacade], output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as stream:
            json.dump([f.to_dict() for f in facades], stream,
                      ensure_ascii=False, indent=2)
        logger.info("Export JSON écrit : %s (%d façade(s))", output_path, len(facades))


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyse d'un plan de façade (DXF)")
    parser.add_argument("dxf_path", help="Chemin du fichier DXF à analyser")
    parser.add_argument("-o", "--output", default="facades_detectees.json",
                        help="Fichier JSON de sortie")
    parser.add_argument("-n", "--level", default=None,
                        help="Niveau le plus bas montré par le plan : RDC, R+1...")
    parser.add_argument("-s", "--scale", type=float, default=1.0,
                        help="Mètres par unité de dessin (0.001 si le DXF est en mm)")
    args = parser.parse_args()

    plan_context = PlanContext.build(view="facade", level=args.level,
                                     level_label=args.level, title=args.dxf_path)
    service = FacadeDetectionService(args.dxf_path, context=plan_context,
                                     unit_scale=args.scale)
    detected = service.detect_facades()
    service.export_json(detected, args.output)

    print("\n=== %d façade(s) détectée(s) ===" % len(detected))
    for facade in detected:
        print("  %-24s %6.2f x %5.2f m  orient=%-6s conf=%.0f  n°=%s"
              % (facade.name, facade.width, facade.height,
                 facade.orientation or "-", facade.confidence,
                 facade.drawing_number or "-"))
        for level in facade.levels:
            print("      niveau %d : %.2f -> %.2f m (h=%.2f m)"
                  % (level.floor_index, level.bottom_elevation,
                     level.top_elevation, level.height))
        for opening in facade.openings:
            print("      %-14s %-6s %5.2f x %4.2f m  allège=%.2f  linteau=%.2f"
                  % (opening.opening_type, opening.mark or "-", opening.width,
                     opening.height, opening.sill_height, opening.lintel_height))
        for feature in facade.features:
            print("      %-14s %5.2f x %4.2f m"
                  % (feature.feature_type, feature.width, feature.height))
