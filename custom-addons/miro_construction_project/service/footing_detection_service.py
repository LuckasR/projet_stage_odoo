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
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

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

# Calques de fondation — correspondance EXACTE (S-SEM ne capte pas S-SEM-FIL)
ISOLATED_FOOTING_LAYER = "S-SEM"
STRIP_FOOTING_LAYER = "S-SEM-FIL"
TIE_BEAM_LAYER = "S-LON"
COLUMN_LAYER = "S-POT"

FOOTING_LAYERS = (ISOLATED_FOOTING_LAYER, STRIP_FOOTING_LAYER,
                  TIE_BEAM_LAYER, COLUMN_LAYER)

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
                 unit_scale: float = 1.0):
        super().__init__(dxf_path)
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
                STRIP_FOOTING_LAYER, TYPE_STRIP, MIN_STRIP_WIDTH, MAX_STRIP_WIDTH)
            + self._detect_linear_footings(
                TIE_BEAM_LAYER, TYPE_TIE_BEAM, MIN_TIE_BEAM_WIDTH, MAX_TIE_BEAM_WIDTH)
        )

        before = len(footings)
        footings = self._deduplicate(footings)
        if before != len(footings):
            logger.info("Déduplication : %d -> %d", before, len(footings))

        for footing in footings:
            footing.level = ctx.level_label

        logger.info("Détection terminée : %d ouvrages de fondation", len(footings))
        return footings

    def to_analysis_result(self, footings: List[DetectedFooting]) -> dict:
        """Résultat complet au format `construction.analysis`."""
        return {
            "schema_version": 1,
            "elements": [f.to_analysis_item() for f in footings],
        }

    # ========================================================
    # OUVRAGES PONCTUELS — contours fermés (S-SEM, S-POT)
    # ========================================================

    def _detect_isolated_footings(self) -> List[DetectedFooting]:
        return self._detect_outline_elements(
            ISOLATED_FOOTING_LAYER, TYPE_ISOLATED,
            MIN_ISOLATED_SIDE, MAX_ISOLATED_SIDE, MAX_ISOLATED_RATIO,
            base_confidence=0.75, label="les semelles isolées")

    def _detect_columns(self) -> List[DetectedFooting]:
        """Poteaux amorcés sur le plan de fondation. Leur section est dessinée
        au centre de la semelle qui les porte : les deux contours se
        superposent mais restent deux ouvrages distincts, sur deux calques
        distincts et de tailles très différentes."""
        return self._detect_outline_elements(
            COLUMN_LAYER, TYPE_COLUMN,
            MIN_COLUMN_SIDE, MAX_COLUMN_SIDE, MAX_COLUMN_RATIO,
            base_confidence=0.75, label="les poteaux")

    def _detect_outline_elements(self, layer: str, type_code: str,
                                 min_side: float, max_side: float,
                                 max_ratio: float, base_confidence: float,
                                 label: str) -> List[DetectedFooting]:
        """Ouvrage ponctuel dessiné comme un contour fermé : sa boîte
        englobante donne directement ses deux côtés."""
        outlines = self.collect_closed_outlines([layer], include_blocks=True)

        if not outlines:
            # Diagnostic utile : distinguer « calque absent » de « calque
            # présent mais dessiné en traits séparés ».
            if self.collect_segments([layer], include_blocks=True):
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

    def _detect_linear_footings(self, layer: str, type_code: str,
                                min_width: float, max_width: float
                                ) -> List[DetectedFooting]:
        segments = self.collect_segments([layer], include_blocks=True)
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
                layer=layer,
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
              f"L={f.length:6.2f}m  l={f.width:5.2f}m  "
              f"repère={'plan' if f.label_found else 'généré'}  "
              f"conf={f.confidence:.2f}")
