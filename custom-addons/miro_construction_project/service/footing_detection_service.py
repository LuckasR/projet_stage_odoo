# -*- coding: utf-8 -*-
"""
footing_detection_service.py
=============================

Détection automatique des ouvrages de fondation dans un plan DXF/DWG.

Quatre ouvrages, quatre calques, deux façons de les dessiner :

    S-SEM       semelle isolée   contour fermé sous un poteau
                                 -> longueur x largeur, position

    S-POT       poteau           contour fermé de la section, amorcé sur le
                                 plan de fondation, au centre de sa semelle
                                 -> longueur x largeur, position

    S-SEM-FIL   semelle filante  bande continue, deux bords parallèles
                                 -> axe, largeur, longueur

    S-LON       longrine         poutre de liaison entre semelles,
                                 deux bords parallèles
                                 -> axe, largeur, longueur

Un ouvrage ponctuel (semelle isolée, poteau) se lit donc comme un contour
fermé, un ouvrage linéaire (filante, longrine) comme une paire de segments
parallèles — exactement comme un mur, d'où la mise en commun de cette
recherche dans `plan_analysis.DxfPlanReader.find_parallel_pairs`.

Tous ces ouvrages sont reconnus par leur GÉOMÉTRIE, jamais par un bloc DXF :
donner un mot-clé de bloc ou de calque à leur type d'élément les rendrait
éligibles au moteur « blocs », qui échouerait en les cherchant parmi les
INSERT du plan (« Aucun bloc du plan ne correspond... »).

Ce que la vue en plan NE donne PAS : la hauteur (ou l'ancrage) de l'ouvrage.
Elle n'est donc jamais inventée — les métrés béton/coffrage restent à
compléter à la validation, et l'anomalie est signalée sur le brouillon.

Le plan de fondation porte aussi l'EMPRISE du bâtiment, d'où se déduit le
dallage du rez-de-chaussée (dallage sur terre-plein) : un brouillon
« DALLAGE » est toujours produit, avec sa surface au nu intérieur des murs
quand l'emprise est lisible, sans surface sinon — le plan de coupes la
complète alors (cf. `detect_ground_slab`).

Le résultat est produit au format attendu par `construction.analysis`
(cf. `_analyze_plan`) : il alimente les brouillons d'éléments, que
l'utilisateur valide avant création des éléments et des phases.

Dépendances :
    pip install ezdxf shapely
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

from shapely.geometry import MultiPoint, MultiPolygon, Polygon
from shapely.ops import unary_union

try:
    from .plan_analysis import VIEW_PLAN, DxfPlanReader, PlanContext, normalize_text
except ImportError:  # exécution directe du module en ligne de commande
    from plan_analysis import (  # type: ignore[no-redef]
        VIEW_PLAN, DxfPlanReader, PlanContext, normalize_text)

logger = logging.getLogger("footing_detection_service")
logging.basicConfig(level=logging.INFO)


# ============================================================
# CONFIGURATION
# ============================================================

# Rôles de calque des fondations (noms : convention de calques du chantier,
# cf. dxf_layers). Les noms livrés sont exacts : S-SEM ne capte pas S-SEM-FIL.
ISOLATED_FOOTING_ROLE = "footing_isolated"
STRIP_FOOTING_ROLE = "footing_strip"
TIE_BEAM_ROLE = "tie_beam"
COLUMN_ROLE = "column"

FOOTING_ROLES = (ISOLATED_FOOTING_ROLE, STRIP_FOOTING_ROLE, TIE_BEAM_ROLE, COLUMN_ROLE)

# Codes de construction.element.type auxquels sont rattachés les ouvrages.
# Ils doivent exister dans Construction > Configuration > Types d'éléments.
TYPE_ISOLATED = "semelle"
TYPE_STRIP = "semelle_filante"
TYPE_TIE_BEAM = "longrine"
TYPE_COLUMN = "poteau"

# Préfixes des repères générés quand le plan n'en porte aucun
KEY_PREFIXES = {
    TYPE_ISOLATED: "SEM",
    TYPE_STRIP: "SF",
    TYPE_TIE_BEAM: "LON",
    TYPE_COLUMN: "POT",
}

# Dimensions plausibles, en mètres
MIN_ISOLATED_SIDE = 0.40
MAX_ISOLATED_SIDE = 5.00
MAX_ISOLATED_RATIO = 4.0      # au-delà, ce n'est plus une semelle isolée

# Section d'un poteau : bien plus petite qu'une semelle, c'est d'ailleurs ce
# qui les distingue quand le poteau est dessiné au centre de sa semelle.
MIN_COLUMN_SIDE = 0.15
MAX_COLUMN_SIDE = 1.50
MAX_COLUMN_RATIO = 6.0        # au-delà, c'est un voile, pas un poteau

MIN_STRIP_WIDTH = 0.30
MAX_STRIP_WIDTH = 2.00

MIN_TIE_BEAM_WIDTH = 0.15
MAX_TIE_BEAM_WIDTH = 0.80

MIN_LINEAR_LENGTH = 0.50      # longueur minimale d'un ouvrage linéaire

# Tolérance d'angle pour juger deux bords « parallèles » (degrés)
PARALLEL_ANGLE_TOLERANCE = 2.0

# Distance max entre un repère textuel et l'ouvrage qu'il désigne (mètres)
MAX_LABEL_DISTANCE = 2.00

# Un repère de fondation ressemble à S1, SF2, LR3, SEM-4, F01, FL02, LG03...
# (« F »/« FL »/« LG » est une convention française tout aussi courante que
# « S »/« SF »/« L » — les deux sont acceptées).
# Le numéro est exigé : un « S » seul, répété sous chaque semelle, ne
# distingue pas les ouvrages entre eux et ne peut pas servir de clé.
# Les préfixes les plus longs sont testés d'abord : sans cela « SF2 » serait
# lu comme un « S » suivi de « F2 ».
LABEL_PATTERN = re.compile(
    r"^\s*(SF|SEM|LON|LR|LG|FL|POT|PO|S|L|F|P)[\s\-_]?\d+[A-Za-z]?\s*$",
    re.IGNORECASE)

# Préfixes de repère admis pour chaque type : sans ce garde-fou, le « SF2 »
# d'une semelle filante est capté par la longrine dessinée juste à côté.
TYPE_LABEL_PREFIXES = {
    TYPE_ISOLATED: ("S", "SEM", "F"),
    TYPE_STRIP: ("SF", "FL"),
    TYPE_TIE_BEAM: ("L", "LR", "LON", "LG"),
    TYPE_COLUMN: ("P", "PO", "POT"),
}

# Déduplication : deux ouvrages dont les centres sont plus proches que ça
# et de mêmes dimensions sont le même ouvrage dessiné deux fois.
DEDUP_TOLERANCE = 0.05

# --- Dallage du rez-de-chaussée --------------------------------------------
TYPE_SLAB = "dalle"
# Repère du brouillon : c'est lui qui distingue le dallage sur terre-plein
# du plancher haut du même niveau (cf. is_ground_slab).
GROUND_SLAB_KEY = "DALLAGE"
# Fond de plan des murs du rez-de-chaussée, repris sur le plan de fondation
WALL_REF_ROLE = "wall_ref"
MIN_WALL_WIDTH = 0.05
MAX_WALL_WIDTH = 0.60
# Les murs sont interrompus par les baies, les longrines par les semelles :
# on referme l'emprise par-dessus les coupures jusqu'à cette largeur (m).
FOOTPRINT_GAP = 3.00
# En deçà, ce n'est pas l'emprise d'un bâtiment (m²)
MIN_FOOTPRINT_AREA = 4.0
# Épaisseur des murs extérieurs supposée quand le plan ne les montre pas (m)
DEFAULT_WALL_THICKNESS = 0.20


def is_ground_slab(key) -> bool:
    """Le brouillon / l'élément est-il le dallage sur terre-plein ?"""
    return (key or "").strip().upper().startswith(GROUND_SLAB_KEY)


# ============================================================
# STRUCTURE DE DONNÉES
# ============================================================

@dataclass
class DetectedFooting:
    """Ouvrage de fondation vu en plan. `height` reste None : une vue en plan
    ne montre pas l'épaisseur de l'ouvrage."""

    key: str
    type_code: str
    layer: str
    geometry_type: str            # "outline" (isolée) ou "line_pair" (linéaire)
    center_x: float
    center_y: float
    length: float                 # plus grande dimension (ou portée)
    width: Optional[float]        # plus petite dimension ; None si non lisible
    bbox: Tuple[float, float, float, float]
    height: Optional[float] = None
    start_x: Optional[float] = None
    start_y: Optional[float] = None
    end_x: Optional[float] = None
    end_y: Optional[float] = None
    level: Optional[str] = None
    label_found: bool = False     # repère lu sur le plan, pas généré
    confidence: float = 0.0       # 0 à 1, échelle des brouillons d'éléments
    issue: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_analysis_item(self) -> dict:
        """Traduction au format attendu par construction.analysis._analyze_plan,
        qui en fait des brouillons d'éléments à valider."""
        dimensions = {"l": round(self.length, 3)}
        if self.width is not None:
            dimensions["w"] = round(self.width, 3)
        if self.height is not None:
            dimensions["h"] = round(self.height, 3)

        return {
            "key": self.key,
            "type": self.type_code,
            "level": self.level or False,
            # Sans hauteur, aucun métré n'est calculable : on ne l'invente pas.
            "quantities": {},
            "dimensions": dimensions,
            "confidence": round(min(max(self.confidence, 0.0), 0.95), 2),
            "issue": self.issue or False,
            "source": {"page": 1, "bbox": list(self.bbox)},
        }


@dataclass
class DetectedGroundSlab:
    """Dallage du rez-de-chaussée, au nu intérieur des murs extérieurs.

    `area` reste None quand l'emprise n'a pas été trouvée : le brouillon est
    créé quand même, le plan de coupes ou la validation le complète."""

    level: Optional[str]
    source: Optional[str] = None          # d'où vient l'emprise (libellé)
    area: Optional[float] = None          # m², nu intérieur
    length: Optional[float] = None        # m, plus grand côté du nu intérieur
    width: Optional[float] = None
    outer_length: Optional[float] = None  # m, emprise extérieure lue
    outer_width: Optional[float] = None
    wall_thickness: Optional[float] = None
    wall_thickness_assumed: bool = False
    bbox: Tuple[float, ...] = ()          # nu intérieur, unités du dessin
    confidence: float = 0.0

    def to_analysis_item(self) -> dict:
        if self.area:
            issues = ["Dallage : emprise %s, %.2f x %.2f m ; surface au nu intérieur "
                      "des murs (%.2f m%s)" % (
                          self.source, self.outer_length, self.outer_width,
                          self.wall_thickness,
                          ", supposés" if self.wall_thickness_assumed else "")]
        else:
            issues = ["Emprise du bâtiment introuvable sur le plan de fondation : "
                      "surface reprise des coupes, ou à saisir"]
        issues.append("Épaisseur du dallage : reprise du plan de coupes, ou à saisir")
        item = {
            "key": GROUND_SLAB_KEY,
            "type": TYPE_SLAB,
            "level": self.level or False,
            "quantities": {"surface_m2": round(self.area, 3)} if self.area else {},
            "dimensions": ({"l": round(self.length, 3), "w": round(self.width, 3)}
                           if self.area else {}),
            "confidence": round(self.confidence, 2),
            "issue": " ; ".join(issues),
            "source": {"page": 1, "bbox": list(self.bbox)},
        }
        return item


# ============================================================
# SERVICE PRINCIPAL
# ============================================================

class FootingDetectionService(DxfPlanReader):
    """Lit un plan de fondation et en extrait semelles isolées, semelles
    filantes et longrines.

    `unit_scale` convertit les unités du dessin en mètres (1.0 si le DXF est
    déjà en mètres, 0.001 s'il est en millimètres). Le modèle Odoo le déduit
    de $INSUNITS, relevé à l'import dans construction.dwg.metadata."""

    # Seule la vue en plan porte la géométrie des fondations. Une coupe
    # donnerait la hauteur des ouvrages : extension à prévoir.
    SUPPORTED_VIEWS = (VIEW_PLAN,)

    def __init__(self, dxf_path: str, context: Optional[PlanContext] = None,
                 unit_scale: float = 1.0, layer_config=None):
        super().__init__(dxf_path, layer_config=layer_config)
        self.context = context or PlanContext()
        self.unit_scale = unit_scale or 1.0
        self._labels: Optional[List[Tuple[str, float, float]]] = None
        self._counters: Dict[str, int] = {}

    # --------------------------------------------------------
    # POINT D'ENTRÉE
    # --------------------------------------------------------

    def detect_footings(self) -> List[DetectedFooting]:
        ctx = self.context
        logger.info("Détection de fondations sur %s (vue=%s, niveau=%s)",
                    self.dxf_path, ctx.view, ctx.level_label or "-")

        if ctx.view not in self.SUPPORTED_VIEWS:
            logger.info("La vue « %s » ne montre pas la géométrie des fondations : "
                        "aucune détection lancée", ctx.view)
            return []

        footings = (
            self._detect_isolated_footings()
            + self._detect_columns()
            + self._detect_linear_footings(
                STRIP_FOOTING_ROLE, TYPE_STRIP, MIN_STRIP_WIDTH, MAX_STRIP_WIDTH)
            + self._detect_linear_footings(
                TIE_BEAM_ROLE, TYPE_TIE_BEAM, MIN_TIE_BEAM_WIDTH, MAX_TIE_BEAM_WIDTH)
        )

        before = len(footings)
        footings = self._deduplicate(footings)
        if before != len(footings):
            logger.info("Déduplication : %d -> %d", before, len(footings))

        for footing in footings:
            footing.level = ctx.level_label

        logger.info("Détection terminée : %d ouvrages de fondation", len(footings))
        return footings

    def to_analysis_result(self, footings: List[DetectedFooting],
                           ground_slab: Optional[DetectedGroundSlab] = None) -> dict:
        """Résultat complet au format `construction.analysis`."""
        elements = [f.to_analysis_item() for f in footings]
        if ground_slab:
            elements.append(ground_slab.to_analysis_item())
        return {"schema_version": 1, "elements": elements}

    # ========================================================
    # DALLAGE DU REZ-DE-CHAUSSÉE — emprise du bâtiment
    # ========================================================

    def detect_ground_slab(self, footings: List[DetectedFooting]) -> DetectedGroundSlab:
        """Dallage sur terre-plein : L x l de la maison, au nu intérieur des
        murs extérieurs. L'emprise est cherchée, dans l'ordre, sur :

          1. les murs de refend       leur nu extérieur, épaisseur lue ;
          2. les longrines            elles courent sous les murs ;
          3. les semelles filantes    idem, plus larges que le mur ;
          4. poteaux / semelles       enveloppe de leurs centres (axes).

        La surface est celle du contour réel (une maison en L n'est pas son
        rectangle englobant). Rien de lisible : surface vide, le plan de
        coupes la complète."""
        slab = DetectedGroundSlab(level=self.context.level_label)

        walls = self._band_footprint(WALL_REF_ROLE, MIN_WALL_WIDTH, MAX_WALL_WIDTH)
        wall_thickness = walls[1] if walls else None
        candidates = [
            ("des murs (%s)" % self.describe_layers(WALL_REF_ROLE), walls, 0.75),
            ("des longrines (%s)" % self.describe_layers(TIE_BEAM_ROLE), self._band_footprint(
                TIE_BEAM_ROLE, MIN_TIE_BEAM_WIDTH, MAX_TIE_BEAM_WIDTH), 0.70),
            ("des semelles filantes (%s)" % self.describe_layers(STRIP_FOOTING_ROLE),
             self._band_footprint(STRIP_FOOTING_ROLE, MIN_STRIP_WIDTH, MAX_STRIP_WIDTH), 0.65),
            ("des poteaux et semelles isolées (axes)", self._point_footprint(footings), 0.45),
        ]
        for label, found, confidence in candidates:
            if not found:
                continue
            outer, band = found
            thickness = wall_thickness or DEFAULT_WALL_THICKNESS
            # Axe de l'ouvrage sous les murs, puis nu intérieur du mur posé
            # dessus : pour les murs eux-mêmes, cela revient à retirer leur
            # épaisseur.
            inner = outer.buffer(-(band + thickness) / 2.0 / self.unit_scale, join_style=2)
            if inner.is_empty or inner.area * self.unit_scale ** 2 < MIN_FOOTPRINT_AREA:
                continue
            s = self.unit_scale
            minx, miny, maxx, maxy = inner.bounds
            ominx, ominy, omaxx, omaxy = outer.bounds
            slab.source = label
            slab.area = inner.area * s * s
            slab.length, slab.width = sorted(((maxx - minx) * s, (maxy - miny) * s), reverse=True)
            slab.outer_length, slab.outer_width = sorted(
                ((omaxx - ominx) * s, (omaxy - ominy) * s), reverse=True)
            slab.wall_thickness = thickness
            slab.wall_thickness_assumed = not wall_thickness
            slab.bbox = (minx, miny, maxx, maxy)
            slab.confidence = confidence
            logger.info("Dallage : emprise %s, %.2f m² au nu intérieur", label, slab.area)
            return slab

        logger.info("Dallage : emprise du bâtiment introuvable sur ce plan")
        return slab

    def _band_footprint(self, role: str, min_width: float, max_width: float
                        ) -> Optional[Tuple[Polygon, float]]:
        """(contour extérieur, largeur de l'ouvrage en m) des ouvrages
        linéaires d'un rôle de calque, réunis et refermés par-dessus leurs
        coupures."""
        s = self.unit_scale
        layers = self.layers(role)
        shapes = [Polygon(o.points).buffer(0)
                  for o in self.collect_closed_outlines(layers, include_blocks=True)
                  if len(o.points) >= 3]
        pairs = self.find_parallel_pairs(
            self.collect_segments(layers, include_blocks=True),
            min_width=min_width / s, max_width=max_width / s,
            min_length=MIN_LINEAR_LENGTH / s, angle_tolerance=PARALLEL_ANGLE_TOLERANCE)
        shapes += [p.axis.buffer(p.width / 2.0, cap_style=2, join_style=2) for p in pairs]
        if not pairs or not shapes:
            return None

        outer = self._outer_contour(shapes)
        if outer is None:
            return None
        # Largeur des ouvrages du pourtour, pas des refends intérieurs
        widths = [p.width * s for p in pairs if p.axis.distance(outer.exterior) <= p.width]
        return outer, statistics.median(widths or [p.width * s for p in pairs])

    def _point_footprint(self, footings: List[DetectedFooting]
                         ) -> Optional[Tuple[Polygon, float]]:
        """Enveloppe des centres des poteaux (à défaut des semelles isolées) :
        les axes du bâtiment, d'où une largeur d'ouvrage nulle."""
        for type_code in (TYPE_COLUMN, TYPE_ISOLATED):
            points = [(f.center_x, f.center_y) for f in footings if f.type_code == type_code]
            if len(points) >= 3:
                hull = MultiPoint(points).convex_hull
                if hull.geom_type == "Polygon":
                    return hull, 0.0
        return None

    def _outer_contour(self, shapes) -> Optional[Polygon]:
        """Contour extérieur de la plus grande pièce, une fois les coupures
        (baies, semelles entre longrines) refermées."""
        gap = FOOTPRINT_GAP / 2.0 / self.unit_scale
        merged = unary_union(shapes).buffer(gap, join_style=2).buffer(-gap, join_style=2)
        pieces = list(merged.geoms) if isinstance(merged, MultiPolygon) else [merged]
        pieces = [p for p in pieces if not p.is_empty]
        if not pieces:
            return None
        outer = Polygon(max(pieces, key=lambda p: p.area).exterior)
        if outer.area * self.unit_scale ** 2 < MIN_FOOTPRINT_AREA:
            return None
        return outer

    # ========================================================
    # OUVRAGES PONCTUELS — contours fermés (semelles isolées, poteaux)
    # ========================================================

    def _detect_isolated_footings(self) -> List[DetectedFooting]:
        return self._detect_outline_elements(
            ISOLATED_FOOTING_ROLE, TYPE_ISOLATED,
            MIN_ISOLATED_SIDE, MAX_ISOLATED_SIDE, MAX_ISOLATED_RATIO,
            base_confidence=0.75, label="les semelles isolées")

    def _detect_columns(self) -> List[DetectedFooting]:
        """Poteaux amorcés sur le plan de fondation. Leur section est dessinée
        au centre de la semelle qui les porte : les deux contours se
        superposent mais restent deux ouvrages distincts, sur deux calques
        distincts et de tailles très différentes."""
        return self._detect_outline_elements(
            COLUMN_ROLE, TYPE_COLUMN,
            MIN_COLUMN_SIDE, MAX_COLUMN_SIDE, MAX_COLUMN_RATIO,
            base_confidence=0.75, label="les poteaux")

    def _detect_outline_elements(self, role: str, type_code: str,
                                 min_side: float, max_side: float,
                                 max_ratio: float, base_confidence: float,
                                 label: str) -> List[DetectedFooting]:
        """Ouvrage ponctuel dessiné comme un contour fermé : sa boîte
        englobante donne directement ses deux côtés."""
        layers = self.layers(role)
        layer = ", ".join(layers) or self.describe_layers(role)
        outlines = self.collect_closed_outlines(layers, include_blocks=True)

        if not outlines:
            # Diagnostic utile : distinguer « calque absent » de « calque
            # présent mais dessiné en traits séparés ».
            if self.collect_segments(layers, include_blocks=True):
                logger.warning(
                    "Calque %s présent mais sans contour fermé : %s doivent "
                    "être des polylignes fermées", layer, label)
            return []

        found: List[DetectedFooting] = []
        for outline in outlines:
            width = min(outline.width, outline.height) * self.unit_scale
            length = max(outline.width, outline.height) * self.unit_scale

            if width < min_side or length > max_side:
                logger.debug("Contour ignoré sur %s (%.2f x %.2f m)",
                             layer, length, width)
                continue
            if width and length / width > max_ratio:
                logger.debug("Contour trop allongé pour %s (%.2f x %.2f m) : "
                             "ignoré", type_code, length, width)
                continue

            cx, cy = outline.center
            found.append(self._build(
                type_code=type_code,
                layer=outline.layer,
                geometry_type="outline",
                center=(cx, cy),
                length=length,
                width=width,
                bbox=(outline.minx, outline.miny, outline.maxx, outline.maxy),
                base_confidence=base_confidence,
            ))

        logger.info("Calque %s : %d contour(s) -> %d ouvrage(s) %s",
                    layer, len(outlines), len(found), type_code)
        return found

    # ========================================================
    # SEMELLES FILANTES ET LONGRINES — paires de bords parallèles
    # ========================================================

    def _detect_linear_footings(self, role: str, type_code: str,
                                min_width: float, max_width: float
                                ) -> List[DetectedFooting]:
        layers = self.layers(role)
        layer = layers[0] if len(layers) == 1 else ", ".join(layers)
        segments = self.collect_segments(layers, include_blocks=True)
        if not segments:
            return []

        # Les seuils sont exprimés en mètres, la géométrie en unités du
        # dessin : on convertit les bornes plutôt que toute la géométrie.
        scale = self.unit_scale
        pairs = self.find_parallel_pairs(
            segments,
            min_width=min_width / scale,
            max_width=max_width / scale,
            min_length=MIN_LINEAR_LENGTH / scale,
            angle_tolerance=PARALLEL_ANGLE_TOLERANCE,
        )
        logger.info("Calque %s : %d segments -> %d ouvrages linéaires",
                    layer, len(segments), len(pairs))

        footings: List[DetectedFooting] = []
        for pair in pairs:
            sx, sy, ex, ey = pair.ends
            cx, cy = pair.center
            footing = self._build(
                type_code=type_code,
                layer=pair.layer_a,
                geometry_type="line_pair",
                center=(cx, cy),
                length=pair.length * scale,
                width=pair.width * scale,
                bbox=(min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey)),
                base_confidence=0.70,
            )
            footing.start_x, footing.start_y = sx, sy
            footing.end_x, footing.end_y = ex, ey
            footings.append(footing)

        footings.extend(self._detect_single_line_footings(
            segments, pairs, layer, type_code))
        return footings

    def _detect_single_line_footings(self, segments, pairs, layer: str,
                                     type_code: str) -> List[DetectedFooting]:
        """Ouvrage tracé en axe simple : une seule ligne, sans bords. C'est
        courant pour les longrines, dont la section est donnée par la
        nomenclature et non par le dessin. On en tire la portée ; la largeur
        reste vide plutôt qu'inventée."""
        scale = self.unit_scale
        min_length = MIN_LINEAR_LENGTH / scale
        footings: List[DetectedFooting] = []

        for line, _layer in segments:
            if line.length < min_length:
                continue
            # Déjà décrit par une paire de bords ? Alors ce n'est pas un axe.
            if any(pair.axis.distance(line) < pair.width
                   and pair.axis.buffer(pair.width).contains(line.centroid)
                   for pair in pairs):
                continue

            (sx, sy), (ex, ey) = line.coords[0], line.coords[-1]
            footing = self._build(
                type_code=type_code,
                layer=layer,
                geometry_type="axis",
                center=((sx + ex) / 2.0, (sy + ey) / 2.0),
                length=line.length * scale,
                width=None,
                bbox=(min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey)),
                base_confidence=0.55,
            )
            footing.start_x, footing.start_y = sx, sy
            footing.end_x, footing.end_y = ex, ey
            footings.append(footing)

        if footings:
            logger.info("Calque %s : %d ouvrages tracés en axe simple "
                        "(largeur non lisible)", layer, len(footings))
        return footings

    # ========================================================
    # CONSTRUCTION D'UN OUVRAGE : REPÈRE, CONFIANCE, ANOMALIES
    # ========================================================

    def _build(self, type_code: str, layer: str, geometry_type: str,
               center: Tuple[float, float], length: float,
               width: Optional[float],
               bbox: Tuple[float, float, float, float],
               base_confidence: float) -> DetectedFooting:
        label = self._find_label(center, type_code)
        issues = []

        if label:
            key = label
        else:
            key = self._generate_key(type_code, center)
            issues.append("Repère généré depuis la position "
                          "(aucun texte de repérage à proximité)")

        if width is None:
            issues.append("Ouvrage tracé en axe simple : largeur à saisir")

        # Une vue en plan ne montre jamais l'épaisseur de l'ouvrage.
        issues.append("Hauteur non lisible sur la vue en plan : "
                      "métrés à compléter à la validation")

        confidence = base_confidence + (0.15 if label else 0.0)

        return DetectedFooting(
            key=key,
            type_code=type_code,
            layer=layer,
            geometry_type=geometry_type,
            center_x=center[0], center_y=center[1],
            length=length, width=width,
            bbox=bbox,
            label_found=bool(label),
            confidence=confidence,
            issue=" ; ".join(issues),
        )

    def _generate_key(self, type_code: str, center: Tuple[float, float]) -> str:
        """Repère stable d'une analyse à l'autre : il dérive de la position,
        donc le même ouvrage retrouve le même brouillon à chaque relance."""
        prefix = KEY_PREFIXES.get(type_code, "EL")
        cx, cy = center
        return "%s_x%d_y%d" % (prefix,
                               round(cx * self.unit_scale * 100),
                               round(cy * self.unit_scale * 100))

    def _find_label(self, center: Tuple[float, float],
                    type_code: str) -> Optional[str]:
        """Repère porté par le plan (« S1 », « SF2 ») le plus proche du centre
        de l'ouvrage, parmi ceux dont le préfixe correspond à son type."""
        if self._labels is None:
            self._labels = []
            for text, x, y in self.collect_texts_with_position():
                match = LABEL_PATTERN.match(text or "")
                if match:
                    self._labels.append(
                        (match.group(1).upper(), text.strip(), x, y))
            logger.info("%d repères de fondation lus sur le plan", len(self._labels))

        allowed = TYPE_LABEL_PREFIXES.get(type_code, ())
        cx, cy = center
        best, best_distance = None, MAX_LABEL_DISTANCE / self.unit_scale

        for prefix, text, x, y in self._labels:
            if prefix not in allowed:
                continue
            distance = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if distance < best_distance:
                best, best_distance = text, distance

        return best

    # ========================================================
    # DÉDUPLICATION
    # ========================================================

    def _deduplicate(self, footings: List[DetectedFooting]) -> List[DetectedFooting]:
        """Un même ouvrage peut ressortir plusieurs fois : contour dessiné en
        double, ou plusieurs paires de bords retenues sur le même axe."""
        kept: List[DetectedFooting] = []

        for footing in sorted(footings, key=lambda f: -f.confidence):
            duplicate = any(
                other.type_code == footing.type_code
                and abs(other.center_x - footing.center_x) < DEDUP_TOLERANCE
                and abs(other.center_y - footing.center_y) < DEDUP_TOLERANCE
                and abs(other.length - footing.length) < DEDUP_TOLERANCE
                and abs((other.width or 0.0) - (footing.width or 0.0)) < DEDUP_TOLERANCE
                for other in kept
            )
            if not duplicate:
                kept.append(footing)

        # Les repères doivent rester uniques : le pipeline des brouillons
        # identifie un élément par (repère, niveau).
        seen: Dict[str, int] = {}
        for footing in kept:
            count = seen.get(footing.key, 0)
            seen[footing.key] = count + 1
            if count:
                footing.key = "%s-%d" % (footing.key, count + 1)
                footing.confidence = max(footing.confidence - 0.1, 0.0)

        return kept

    # --------------------------------------------------------
    # EXPORT
    # --------------------------------------------------------

    def export_json(self, footings: List[DetectedFooting], output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.to_analysis_result(footings), f,
                      ensure_ascii=False, indent=2)
        logger.info("Export JSON écrit : %s (%d ouvrages)", output_path, len(footings))


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Détection des fondations (semelles, longrines) dans un DXF")
    parser.add_argument("dxf_path", help="Chemin du fichier DXF à analyser")
    parser.add_argument("-o", "--output", default="fondations_detectees.json",
                        help="Fichier JSON de sortie")
    parser.add_argument("-n", "--level", default=None,
                        help="Niveau du plan : Fondation, Sous-sol...")
    parser.add_argument("-s", "--scale", type=float, default=1.0,
                        help="Mètres par unité de dessin (0.001 si le DXF est en mm)")
    args = parser.parse_args()

    plan_context = PlanContext.build(view="plan", level=args.level,
                                     level_label=args.level, title=args.dxf_path)
    service = FootingDetectionService(args.dxf_path, context=plan_context,
                                      unit_scale=args.scale)
    detected = service.detect_footings()
    service.export_json(detected, args.output)

    print(f"\n=== {len(detected)} ouvrages de fondation détectés ===")
    for f in detected:
        print(f"  {f.key:16s} {f.type_code:16s} [{f.layer:10s}] "
              f"L={f.length:6.2f}m  l={(f.width or 0.0):5.2f}m  "
              f"repère={'plan' if f.label_found else 'généré'}  "
              f"conf={f.confidence:.2f}")
    ground = service.detect_ground_slab(detected)
    if ground.area:
        print(f"  DALLAGE : emprise {ground.source} {ground.outer_length:.2f} x "
              f"{ground.outer_width:.2f} m -> {ground.area:.2f} m² au nu intérieur")
    else:
        print("  DALLAGE : emprise introuvable (surface à reprendre des coupes)")
