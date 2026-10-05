# -*- coding: utf-8 -*-
"""
wall_detection_service.py
==========================

Détection automatique des murs dans un fichier DXF/DWG, puis consolidation
progressive des murs d'un même niveau au fil des plans importés.

Principe général
----------------
Un plan est classé par trois axes (choisis à l'import) :

    type de plan  (Architecture, Fondation, Structure...)
    type de vue   (Plan, Coupe, Façade, Détail, Schéma, 3D)
    niveau        (Sous-sol, Fondation, R+0, R+1...)

Chaque vue ne montre qu'une partie de la réalité d'un mur : on n'extrait donc
que ce que la vue permet réellement de voir, et on laisse VIDE le reste.

    Vue en plan  -> position, longueur, épaisseur, intérieur/extérieur
                    (la hauteur n'est pas visible : laissée vide)
    Vue façade   -> hauteur et longueur de la façade + orientation
                    (l'épaisseur n'est pas visible : laissée vide)
    Vue coupe    -> hauteur (et épaisseur) sous plafond du niveau
                    (la position en plan n'est pas visible : laissée vide)

Un import ultérieur sur le MÊME niveau vient compléter les champs restés
vides des murs déjà connus, sans jamais écraser une valeur déjà renseignée
(cf. `merge_detected_walls`). Exemple du cycle attendu :

    1. Architecture + Façade + R+0  -> « Mur façade nord » : hauteur 3.00 m,
                                       épaisseur/position vides
    2. Architecture + Plan   + R+0  -> le même mur reçoit sa longueur, son
                                       épaisseur et sa géométrie ; sa hauteur
                                       déjà connue est conservée

Détection géométrique (vue en plan)
-----------------------------------
Seuls les calques A-MUR-EXT et A-MUR-INT sont analysés. Sur ces calques, les
murs peuvent être dessinés soit comme POLYLINE fermée traçant le contour du
mur, soit comme LINE simple. On décompose donc toutes ces entités en segments
et on détecte les paires de segments parallèles distants d'une épaisseur de
mur plausible : l'axe médian de la paire est l'axe du mur.

Dépendances :
    pip install ezdxf shapely
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

from shapely.geometry import LineString, Point
from shapely.ops import unary_union, linemerge

try:
    from .plan_analysis import (
        LEVEL_WILDCARD, ORIENTATIONS, VIEW_ELEVATION, VIEW_PLAN, VIEW_SECTION,
        DxfPlanReader, Outline, PlanContext, find_orientation, normalize_text,
        normalize_view,
    )
except ImportError:  # exécution directe du module en ligne de commande
    from plan_analysis import (  # type: ignore[no-redef]
        LEVEL_WILDCARD, ORIENTATIONS, VIEW_ELEVATION, VIEW_PLAN, VIEW_SECTION,
        DxfPlanReader, Outline, PlanContext, find_orientation, normalize_text,
        normalize_view,
    )

logger = logging.getLogger("wall_detection_service")
logging.basicConfig(level=logging.INFO)


# ============================================================
# CONFIGURATION
# ============================================================

# Calques contenant les murs — correspondance EXACTE (insensible à la casse)
WALL_LAYERS = ["A-MUR-EXT", "A-MUR-INT"]

# Calques du contour de façade : sur un vrai plan de façade, le mur n'est
# JAMAIS redessiné sur les calques A-MUR-* (ceux-ci restent vides sur ce
# type de plan) — il est tracé sur un calque dédié à la vue. On cherche donc
# les deux familles en vue façade et en coupe, sans a priori sur laquelle
# le bureau d'études a utilisée.
FACADE_LAYERS = ["A-FAC-CONT"]
ELEVATION_SECTION_LAYERS = WALL_LAYERS + FACADE_LAYERS

# Calque des détails de façade : fenêtres, portes, ET la dalle de plancher
# entre deux niveaux, dessinée comme deux traits horizontaux parallèles.
FACADE_DETAIL_LAYERS = ["A-FAC-DET"]

# Distance max entre le centre d'un bloc de façade et le texte qui porte son
# orientation (« FACADE NORD »), en mètres.
FACADE_LABEL_MAX_DISTANCE = 8.0

# Une dalle traverse (presque) toute la largeur du bloc ; un linteau ou un
# appui de fenêtre ne fait que quelques dizaines de centimètres. C'est ce qui
# les distingue, bien plus que leur épaisseur.
SLAB_MIN_LENGTH_RATIO = 0.5
SLAB_MIN_THICKNESS = 0.05
SLAB_MAX_THICKNESS = 0.50
# Tolérance angulaire pour juger une dalle « horizontale » (degrés depuis 0°)
SLAB_ANGLE_TOLERANCE = 10.0

# Calque des hachures de mur (utilisé uniquement pour valider la confiance)
WALL_HATCH_LAYER = "A-MUR-HACH"

# Épaisseur plausible d'un mur, en mètres
MIN_WALL_THICKNESS = 0.05    # 5 cm
MAX_WALL_THICKNESS = 0.80    # 80 cm

# Hauteur plausible d'un mur, en mètres (vues façade et coupe)
MIN_WALL_HEIGHT = 1.50
MAX_WALL_HEIGHT = 15.00

# Longueur minimale d'un segment pour qu'il soit considéré comme un mur
MIN_WALL_LENGTH = 0.30

# Seuil de confiance minimal pour retenir un mur détecté
MIN_CONFIDENCE_THRESHOLD = 50.0

# Tolérance d'angle pour juger deux segments "parallèles" (degrés)
PARALLEL_ANGLE_TOLERANCE = 2.0

# Tolérance pour fusionner des segments colinéaires (mètres)
COLINEAR_MERGE_TOLERANCE = 0.02

# Distance max entre deux axes pour les considérer comme le même mur (mètres)
SAME_WALL_TOLERANCE = 0.25

# Regroupement des murs qui se chevauchent (option « Regrouper » à l'import).
# Deux murs ne sont regroupés que s'ils décrivent manifestement le même mur :
#   - parallèles (PARALLEL_ANGLE_TOLERANCE) ;
#   - sur le même axe : l'autre coordonnée (y pour un mur horizontal, x pour
#     un vertical, distance à l'axe en général) ne s'écarte pas de plus de
#     OVERLAP_AXIS_TOLERANCE ;
#   - de même épaisseur, à OVERLAP_THICKNESS_TOLERANCE près ;
#   - qui se recouvrent réellement le long de l'axe, d'au moins
#     OVERLAP_MIN_LENGTH (deux murs bout à bout ne se chevauchent pas : ils
#     relèvent de la fusion colinéaire, qui exige le même calque).
# Le regroupement est transitif : L1 2->12, L2 6->8, L3 3->20 donnent un
# seul mur 2->20.
OVERLAP_AXIS_TOLERANCE = 0.05
OVERLAP_THICKNESS_TOLERANCE = 0.02
OVERLAP_MIN_LENGTH = 0.01

# Part de la largeur/hauteur du bâtiment définissant la bande « de façade »
FACADE_BAND_RATIO = 0.25


# ============================================================
# TYPES DE VUE EXPLOITABLES POUR LES MURS
# ============================================================

# Un mur se lit en plan (position), en façade (hauteur) et en coupe
# (hauteur sous plafond). Les autres vues ne portent rien d'exploitable.
SUPPORTED_VIEWS = (VIEW_PLAN, VIEW_ELEVATION, VIEW_SECTION)


# ============================================================
# STRUCTURE DE DONNÉES — MIROIR DU MODELE ODOO construction.wall
# ============================================================

# Champs vus comme « non renseignés » : la fusion ne remplit que ceux-là.
EMPTY_SELECTION_VALUES = ("unknown", "", None, False)


@dataclass
class DetectedWall:
    """Mur tel que vu par UNE vue. Tout champ que la vue ne permet pas
    d'observer vaut None et sera laissé vide côté Odoo, en attendant un plan
    d'une autre vue qui le renseignera."""

    name: str
    match_key: str = ""
    source_view: str = VIEW_PLAN
    level: Optional[str] = None
    orientation: Optional[str] = None
    layer: Optional[str] = None
    wall_type: str = "unknown"
    material: str = "unknown"
    geometry_type: str = "unknown"
    start_x: Optional[float] = None
    start_y: Optional[float] = None
    end_x: Optional[float] = None
    end_y: Optional[float] = None
    center_x: Optional[float] = None
    center_y: Optional[float] = None
    points: Optional[str] = None
    length: Optional[float] = None
    thickness: Optional[float] = None
    height: Optional[float] = None
    confidence: float = 0.0
    detection_method: str = "layer"

    # Étage détecté sur une façade multi-niveaux (0 = le plus bas du bloc),
    # avant résolution vers un construction.plan.level réel. Le service ne
    # connaît pas vos niveaux : c'est l'appelant (construction_file.py) qui
    # résout floor_index vers un niveau concret, via dwg.level_ids triés par
    # élévation. None = mur déjà rattaché à un niveau unique par le contexte
    # (vue en plan, coupe, ou façade à un seul bloc / sans dalle détectée).
    floor_index: Optional[int] = None

    # Champs transmis tels quels au modèle Odoo construction.wall
    ODOO_FIELDS = (
        "name", "match_key", "orientation", "layer", "wall_type", "material",
        "geometry_type", "start_x", "start_y", "end_x", "end_y",
        "center_x", "center_y", "points", "length", "thickness", "height",
        "confidence", "detection_method",
    )

    def to_odoo_dict(self) -> dict:
        """Dict complet (export JSON, débogage)."""
        return asdict(self)

    def to_odoo_vals(self) -> dict:
        """Valeurs à écrire dans construction.wall : les champs non observés
        (None) sont omis pour rester vides en base."""
        vals = {}
        for name in self.ODOO_FIELDS:
            value = getattr(self, name)
            if value is not None:
                vals[name] = value
        return vals

    @property
    def is_level_wide(self) -> bool:
        """Mur « générique » décrivant tout le niveau (cas de la coupe) :
        il complète les murs existants plutôt que d'en désigner un seul."""
        return self.match_key.endswith("|%s" % LEVEL_WILDCARD)

    @property
    def has_axis(self) -> bool:
        return None not in (self.start_x, self.start_y, self.end_x, self.end_y)


# ============================================================
# SERVICE PRINCIPAL
# ============================================================

class WallDetectionService(DxfPlanReader):
    """Lit un DXF et en extrait des murs, selon ce que la vue permet de voir."""

    def __init__(self, dxf_path: str, context: Optional[PlanContext] = None,
                 merge_overlaps: bool = False):
        super().__init__(dxf_path)
        self.context = context or PlanContext()
        # Regrouper en un seul mur les murs qui se chevauchent sur un même axe
        # (cf. _merge_overlapping_walls). Vue en plan uniquement.
        self.merge_overlaps = merge_overlaps
        self._wall_counter = 0

    # --------------------------------------------------------
    # POINT D'ENTRÉE — aiguillage selon le type de vue
    # --------------------------------------------------------

    def detect_walls(self) -> List[DetectedWall]:
        ctx = self.context
        logger.info("Détection sur %s (vue=%s, niveau=%s)",
                    self.dxf_path, ctx.view, ctx.level_label or "-")

        if not ctx.is_supported:
            logger.info("La vue « %s » ne permet pas d'extraire de murs : "
                        "aucune détection lancée", ctx.view)
            return []

        detectors = {
            VIEW_PLAN: self._detect_from_plan_view,
            VIEW_ELEVATION: self._detect_from_elevation_view,
            VIEW_SECTION: self._detect_from_section_view,
        }
        walls = detectors[ctx.view]()

        for wall in walls:
            # Un mur d'étage (floor_index posé) attend sa résolution par
            # l'appelant : lui donner ctx.level écraserait le niveau réel une
            # fois résolu, ou masquerait l'absence de résolution.
            if wall.floor_index is None:
                wall.level = ctx.level
            wall.source_view = ctx.view

        logger.info("Détection terminée : %d murs retenus (vue %s)",
                    len(walls), ctx.view)
        return walls

    # ========================================================
    # VUE EN PLAN — position, longueur, épaisseur
    # (la hauteur n'est pas observable : laissée vide)
    # ========================================================

    def _detect_from_plan_view(self) -> List[DetectedWall]:
        segments = self._collect_wall_segments()
        logger.info("Segments collectés sur %s : %d", WALL_LAYERS, len(segments))

        if not segments:
            logger.warning("Aucun segment trouvé sur les calques murs — "
                           "vérifie l'orthographe des calques dans le DXF")
            return []

        walls = self._detect_from_parallel_segments(segments)
        logger.info("Étape 1 (paires parallèles) : %d murs candidats", len(walls))

        hatch_points = self._collect_hatch_points()
        self._cross_validate_with_hatches(walls, hatch_points)

        before = len(walls)
        walls = self._merge_colinear_walls(walls)
        logger.info("Étape 2 (fusion colinéaire) : %d -> %d", before, len(walls))

        if self.merge_overlaps:
            before = len(walls)
            walls = self._merge_overlapping_walls(walls)
            logger.info("Étape 2b (regroupement des chevauchements) : %d -> %d",
                        before, len(walls))

        before = len(walls)
        walls = self._filter_plausible_walls(walls)
        logger.info("Étape 3 (filtrage) : %d -> %d", before, len(walls))

        before = len(walls)
        walls = self._deduplicate_walls(walls)
        logger.info("Étape 4 (déduplication) : %d -> %d", before, len(walls))

        self._assign_plan_orientations(walls)
        return walls

    # --------------------------------------------------------
    # COLLECTE PROPRE AUX MURS (le reste vient de DxfPlanReader)
    # --------------------------------------------------------

    def _collect_wall_segments(self):
        return self.collect_segments(WALL_LAYERS)

    def _collect_hatch_points(self) -> List[Point]:
        """Points médians des petites lignes de hachure sur A-MUR-HACH.
        Sert uniquement à valider la position d'un mur (bonus de confiance)."""
        points: List[Point] = []
        try:
            for e in self.msp.query(f'LINE[layer=="{WALL_HATCH_LAYER}"]'):
                mx = (e.dxf.start.x + e.dxf.end.x) / 2.0
                my = (e.dxf.start.y + e.dxf.end.y) / 2.0
                points.append(Point(mx, my))
        except Exception as exc:
            logger.debug("Erreur collecte hachures : %s", exc)
        return points

    # --------------------------------------------------------
    # DÉTECTION PAR PAIRES DE SEGMENTS PARALLÈLES
    # --------------------------------------------------------

    def _detect_from_parallel_segments(
        self, segments: List[Tuple[LineString, str]]
    ) -> List[DetectedWall]:
        """Un mur vu en plan, c'est deux faces parallèles écartées d'une
        épaisseur plausible. La recherche des paires est commune à tous les
        ouvrages linéaires (cf. DxfPlanReader.find_parallel_pairs) ; ici on
        ne fait qu'en traduire le résultat en murs."""
        walls: List[DetectedWall] = []

        for pair in self.find_parallel_pairs(
                segments,
                min_width=MIN_WALL_THICKNESS,
                max_width=MAX_WALL_THICKNESS,
                min_length=MIN_WALL_LENGTH,
                angle_tolerance=PARALLEL_ANGLE_TOLERANCE):

            layer = self._best_layer(pair.layer_a, pair.layer_b)
            self._wall_counter += 1
            sx, sy, ex, ey = pair.ends
            cx, cy = pair.center

            walls.append(DetectedWall(
                name=f"Mur {self._wall_counter}",
                layer=layer,
                wall_type="exterior" if self._is_exterior_layer(layer) else "interior",
                material="unknown",
                geometry_type="line_pair",
                start_x=sx, start_y=sy,
                end_x=ex, end_y=ey,
                center_x=cx, center_y=cy,
                length=pair.length,
                thickness=pair.width,
                # hauteur non observable sur une vue en plan
                height=None,
                confidence=85.0,
                detection_method="layer",
            ))

        return walls

    def _is_exterior_layer(self, layer: Optional[str]) -> bool:
        """« A-MUR-EXT », « MURS_EXT »... : la convention de nommage varie d'un
        bureau d'études à l'autre, seul le marqueur « ext » est constant."""
        return "ext" in normalize_text(layer)

    def _best_layer(self, la: str, lb: str) -> str:
        """Une paire de segments à cheval sur les deux calques décrit la face
        extérieure d'un mur extérieur."""
        return la if self._is_exterior_layer(la) else lb if self._is_exterior_layer(lb) else la

    # --------------------------------------------------------
    # VALIDATION CROISÉE AVEC LES HACHURES
    # --------------------------------------------------------

    def _cross_validate_with_hatches(
        self, walls: List[DetectedWall], hatch_points: List[Point]
    ) -> None:
        if not hatch_points:
            return
        for wall in walls:
            axis = LineString([
                (wall.start_x, wall.start_y),
                (wall.end_x, wall.end_y),
            ])
            max_dist = max(wall.thickness * 1.5, 0.20)
            for p in hatch_points:
                if axis.distance(p) < max_dist:
                    wall.confidence = min(wall.confidence + 5.0, 99.0)
                    break

    # --------------------------------------------------------
    # FUSION DES MURS COLINÉAIRES ET CONTIGUS
    # --------------------------------------------------------

    def _merge_colinear_walls(self, walls: List[DetectedWall]) -> List[DetectedWall]:
        """Fusionne deux murs du même calque, colinéaires et dont les
        extrémités se touchent (à COLINEAR_MERGE_TOLERANCE près)."""
        if not walls:
            return walls

        by_layer = {}
        for w in walls:
            by_layer.setdefault(w.layer, []).append(w)

        merged_walls: List[DetectedWall] = []

        for layer, layer_walls in by_layer.items():
            remaining = list(layer_walls)

            while remaining:
                base = remaining.pop(0)
                base_line = LineString([
                    (base.start_x, base.start_y),
                    (base.end_x, base.end_y),
                ])
                base_angle = self.line_angle(base_line)

                to_merge = []
                for other in remaining[:]:
                    other_line = LineString([
                        (other.start_x, other.start_y),
                        (other.end_x, other.end_y),
                    ])
                    other_angle = self.line_angle(other_line)
                    angle_diff = min(
                        abs(base_angle - other_angle),
                        180 - abs(base_angle - other_angle),
                    )
                    if angle_diff > PARALLEL_ANGLE_TOLERANCE:
                        continue
                    if base_line.distance(other_line) > COLINEAR_MERGE_TOLERANCE:
                        continue
                    if not self._are_contiguous(base_line, other_line):
                        continue
                    to_merge.append(other)
                    remaining.remove(other)

                if not to_merge:
                    merged_walls.append(base)
                    continue

                all_lines = [base_line] + [
                    LineString([(w.start_x, w.start_y), (w.end_x, w.end_y)])
                    for w in to_merge
                ]
                try:
                    union = unary_union(all_lines)
                    merged = linemerge(union)
                    merged_list = (
                        [merged] if merged.geom_type == "LineString"
                        else list(merged.geoms)
                    )
                except Exception as exc:
                    logger.warning("Fusion impossible (%s), murs conservés", exc)
                    merged_walls.append(base)
                    merged_walls.extend(to_merge)
                    continue

                all_walls = [base] + to_merge
                avg_thickness = sum(w.thickness for w in all_walls) / len(all_walls)
                avg_conf = sum(w.confidence for w in all_walls) / len(all_walls)

                for ml in merged_list:
                    (sx, sy), (ex, ey) = ml.coords[0], ml.coords[-1]
                    self._wall_counter += 1
                    merged_walls.append(DetectedWall(
                        name=f"Mur {self._wall_counter}",
                        layer=layer,
                        wall_type=base.wall_type,
                        material=base.material,
                        geometry_type="line_pair",
                        start_x=sx, start_y=sy,
                        end_x=ex, end_y=ey,
                        center_x=(sx + ex) / 2.0,
                        center_y=(sy + ey) / 2.0,
                        length=ml.length,
                        thickness=avg_thickness,
                        height=base.height,
                        confidence=min(avg_conf + 3.0, 99.0),
                        detection_method="combined",
                    ))

        return merged_walls

    # --------------------------------------------------------
    # REGROUPEMENT DES MURS QUI SE CHEVAUCHENT
    # --------------------------------------------------------

    @staticmethod
    def _axis_frame(wall: DetectedWall):
        """Repère de l'axe d'un mur : origine, vecteur unitaire de direction
        et normale. Projeter un point dessus donne (abscisse le long du mur,
        écart à l'axe)."""
        dx, dy = wall.end_x - wall.start_x, wall.end_y - wall.start_y
        norm = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / norm, dy / norm
        return (wall.start_x, wall.start_y), (ux, uy), (-uy, ux)

    @staticmethod
    def _project(frame, x: float, y: float) -> Tuple[float, float]:
        (ox, oy), (ux, uy), (nx, ny) = frame
        px, py = x - ox, y - oy
        return px * ux + py * uy, px * nx + py * ny

    def _overlaps(self, a: DetectedWall, b: DetectedWall) -> bool:
        """`b` décrit-il le même mur que `a`, en le recouvrant au moins en
        partie ? (cf. constantes OVERLAP_*)."""
        if abs((a.thickness or 0.0) - (b.thickness or 0.0)) > OVERLAP_THICKNESS_TOLERANCE:
            return False

        angle_a = self.line_angle(LineString([(a.start_x, a.start_y), (a.end_x, a.end_y)]))
        angle_b = self.line_angle(LineString([(b.start_x, b.start_y), (b.end_x, b.end_y)]))
        diff = abs(angle_a - angle_b) % 180.0
        if min(diff, 180.0 - diff) > PARALLEL_ANGLE_TOLERANCE:
            return False

        frame = self._axis_frame(a)
        sb, ob = self._project(frame, b.start_x, b.start_y)
        eb, oe = self._project(frame, b.end_x, b.end_y)
        # Même axe : les deux extrémités de b sont sur la ligne de a.
        if max(abs(ob), abs(oe)) > OVERLAP_AXIS_TOLERANCE:
            return False

        # Recouvrement réel des deux intervalles le long de l'axe.
        lo_b, hi_b = sorted((sb, eb))
        overlap = min(a.length, hi_b) - max(0.0, lo_b)
        return overlap >= OVERLAP_MIN_LENGTH

    def _merge_overlapping_walls(self, walls: List[DetectedWall]) -> List[DetectedWall]:
        """Regroupe en un seul mur les murs parallèles, de même épaisseur et
        sur le même axe, qui se recouvrent (un mur redessiné en plusieurs
        morceaux qui s'enchevêtrent, ou tracé à la fois sur A-MUR-EXT et
        A-MUR-INT).

        Les groupes se forment de proche en proche (union-find) : un morceau
        qui en recouvre deux autres les réunit tous. Le mur obtenu va de
        l'extrémité la plus basse à la plus haute du groupe, le long de l'axe
        du morceau le plus long."""
        n = len(walls)
        if n < 2:
            return walls

        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(n):
            for j in range(i + 1, n):
                if find(i) != find(j) and self._overlaps(walls[i], walls[j]):
                    parent[find(j)] = find(i)

        groups: Dict[int, List[DetectedWall]] = {}
        for i, wall in enumerate(walls):
            groups.setdefault(find(i), []).append(wall)

        result: List[DetectedWall] = []
        for group in groups.values():
            if len(group) == 1:
                result.append(group[0])
                continue
            result.append(self._merge_wall_group(group))
        return result

    def _merge_wall_group(self, group: List[DetectedWall]) -> DetectedWall:
        base = max(group, key=lambda w: w.length)
        frame = self._axis_frame(base)
        (ox, oy), (ux, uy), (nx, ny) = frame

        along, offsets = [], []
        for w in group:
            for x, y in ((w.start_x, w.start_y), (w.end_x, w.end_y)):
                t, o = self._project(frame, x, y)
                along.append(t)
                offsets.append(o)
        t_min, t_max = min(along), max(along)
        # Axe commun : moyenne des écarts, tous inférieurs à la tolérance.
        offset = sum(offsets) / len(offsets)

        sx, sy = ox + ux * t_min + nx * offset, oy + uy * t_min + ny * offset
        ex, ey = ox + ux * t_max + nx * offset, oy + uy * t_max + ny * offset

        total = sum(w.length for w in group) or 1.0
        thickness = sum(w.thickness * w.length for w in group) / total

        # Un morceau tracé sur un calque extérieur fait du mur un mur extérieur.
        exterior = next((w for w in group if self._is_exterior_layer(w.layer)), None)
        ref = exterior or base

        self._wall_counter += 1
        logger.debug("Regroupement de %d murs qui se chevauchent : %s",
                     len(group), ", ".join(w.name for w in group))
        return DetectedWall(
            name=f"Mur {self._wall_counter}",
            layer=ref.layer,
            wall_type=ref.wall_type,
            material=base.material,
            geometry_type="line_pair",
            start_x=sx, start_y=sy,
            end_x=ex, end_y=ey,
            center_x=(sx + ex) / 2.0,
            center_y=(sy + ey) / 2.0,
            length=t_max - t_min,
            thickness=thickness,
            height=base.height,
            confidence=min(max(w.confidence for w in group) + 2.0, 99.0),
            detection_method="combined",
        )

    def _are_contiguous(self, la: LineString, lb: LineString) -> bool:
        pa = [Point(la.coords[0]), Point(la.coords[-1])]
        pb = [Point(lb.coords[0]), Point(lb.coords[-1])]
        for p1 in pa:
            for p2 in pb:
                if p1.distance(p2) < COLINEAR_MERGE_TOLERANCE:
                    return True
        return False

    # --------------------------------------------------------
    # FILTRAGE / DÉDUPLICATION
    # --------------------------------------------------------

    def _filter_plausible_walls(self, walls: List[DetectedWall]) -> List[DetectedWall]:
        return [
            w for w in walls
            if w.length >= MIN_WALL_LENGTH
            and MIN_WALL_THICKNESS <= w.thickness <= MAX_WALL_THICKNESS
            and w.confidence >= MIN_CONFIDENCE_THRESHOLD
        ]

    def _deduplicate_walls(self, walls: List[DetectedWall]) -> List[DetectedWall]:
        DEDUP_TOLERANCE = 0.05
        kept: List[DetectedWall] = []

        for wall in sorted(walls, key=lambda w: -w.confidence):
            is_dup = False
            for existing in kept:
                same_ends = (
                    abs(wall.start_x - existing.start_x) < DEDUP_TOLERANCE
                    and abs(wall.start_y - existing.start_y) < DEDUP_TOLERANCE
                    and abs(wall.end_x - existing.end_x) < DEDUP_TOLERANCE
                    and abs(wall.end_y - existing.end_y) < DEDUP_TOLERANCE
                )
                rev_ends = (
                    abs(wall.start_x - existing.end_x) < DEDUP_TOLERANCE
                    and abs(wall.start_y - existing.end_y) < DEDUP_TOLERANCE
                    and abs(wall.end_x - existing.start_x) < DEDUP_TOLERANCE
                    and abs(wall.end_y - existing.start_y) < DEDUP_TOLERANCE
                )
                same_center = (
                    abs(wall.center_x - existing.center_x) < DEDUP_TOLERANCE
                    and abs(wall.center_y - existing.center_y) < DEDUP_TOLERANCE
                )
                similar_length = abs(wall.length - existing.length) < DEDUP_TOLERANCE
                similar_thickness = abs(wall.thickness - existing.thickness) < DEDUP_TOLERANCE

                if (same_ends or rev_ends) and similar_length:
                    is_dup = True
                    break
                if same_center and similar_length and similar_thickness:
                    is_dup = True
                    break

            if not is_dup:
                kept.append(wall)

        return kept

    # --------------------------------------------------------
    # ORIENTATION DES MURS DE FAÇADE (vue en plan)
    # --------------------------------------------------------

    def _assign_plan_orientations(self, walls: List[DetectedWall]) -> None:
        """Donne une orientation cardinale aux murs extérieurs, d'après leur
        position dans l'emprise du bâtiment. C'est ce qui permet au mur
        « nord » d'une vue en plan de rejoindre le mur d'une vue de façade
        nord du même niveau.

        Seul le mur extérieur le plus long de chaque orientation porte la clé
        de façade : les autres gardent une clé géométrique pour ne pas se
        rapporter tous au même mur."""
        ctx = self.context
        exteriors = [w for w in walls if w.wall_type == "exterior"]

        if exteriors:
            xs = [w.center_x for w in exteriors]
            ys = [w.center_y for w in exteriors]
            minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
            band_x = (maxx - minx) * FACADE_BAND_RATIO
            band_y = (maxy - miny) * FACADE_BAND_RATIO

            # Sans étendue sur un axe, opposer les deux façades de cet axe
            # n'a pas de sens : tous les murs y seraient du même côté.
            spread_x = (maxx - minx) > MIN_WALL_LENGTH
            spread_y = (maxy - miny) > MIN_WALL_LENGTH

            for wall in exteriors:
                angle = self.line_angle(LineString([
                    (wall.start_x, wall.start_y), (wall.end_x, wall.end_y)]))
                is_horizontal = angle < 45 or angle > 135
                if is_horizontal and spread_y:
                    if wall.center_y >= maxy - band_y:
                        wall.orientation = "nord"
                    elif wall.center_y <= miny + band_y:
                        wall.orientation = "sud"
                elif not is_horizontal and spread_x:
                    if wall.center_x >= maxx - band_x:
                        wall.orientation = "est"
                    elif wall.center_x <= minx + band_x:
                        wall.orientation = "ouest"

        facade_holders = {}
        walls_by_side = {}
        for orientation in ORIENTATIONS:
            candidates = [w for w in exteriors if w.orientation == orientation]
            if not candidates:
                continue
            # Titulaire de la clé de façade : toujours le plus long
            facade_holders[orientation] = max(candidates, key=lambda w: w.length)
            # Numérotation dans l'ordre géométrique, le long du côté
            if orientation in ("nord", "sud"):
                candidates.sort(key=lambda w: w.center_x)   # ouest -> est
            else:
                candidates.sort(key=lambda w: w.center_y)   # sud -> nord
            walls_by_side[orientation] = candidates

        # NOMS : tous les murs d'un côté s'appellent « Mur façade <côté> N »
        for orientation, side_walls in walls_by_side.items():
            for index, wall in enumerate(side_walls, start=1):
                if len(side_walls) > 1:
                    wall.name = "Mur façade %s %d" % (orientation, index)
                else:
                    wall.name = "Mur façade %s" % orientation

        # CLÉS : une seule clé « facade-<côté> », réservée au titulaire
        for wall in walls:
            holder = facade_holders.get(wall.orientation)
            if holder is wall:
                wall.match_key = ctx.match_key("facade-%s" % wall.orientation)
            else:
                wall.match_key = ctx.match_key(
                    "axe-%.2f-%.2f" % (wall.center_x, wall.center_y))

    # ========================================================
    # VUE FAÇADE — hauteur, longueur et orientation
    # (l'épaisseur et la position en plan restent vides)
    #
    # Un même plan de façade montre souvent plusieurs orientations et
    # plusieurs niveaux à la fois (Nord/Sud/Est/Ouest, RDC+R1...), chaque
    # bloc portant son propre texte « FACADE NORD » et une dalle qui sépare
    # ses étages. On détecte donc un mur PAR ÉTAGE ET PAR BLOC, pas un seul
    # mur pour tout le fichier.
    # ========================================================

    def _detect_from_elevation_view(self) -> List[DetectedWall]:
        blocks = [
            outline for outline in self.collect_closed_outlines(ELEVATION_SECTION_LAYERS)
            if MIN_WALL_HEIGHT <= outline.height <= MAX_WALL_HEIGHT
        ]

        if not blocks:
            # Aucun contour fermé : plan dessiné en traits ouverts. On
            # retombe sur l'emprise globale, sans découpe par bloc ni dalle.
            return self._detect_elevation_fallback()

        label_texts = [
            (text, x, y) for text, x, y in self.collect_texts_with_position()
            if find_orientation(text)
        ]
        single_block = len(blocks) == 1

        walls: List[DetectedWall] = []
        for block in blocks:
            orientation = self._block_orientation(block, label_texts)
            if not orientation and single_block:
                # Repli historique : un seul bloc, pas de texte « FACADE » à
                # proximité — on tente le nom du fichier.
                orientation = find_orientation(self.context.title)

            bands = self._split_block_by_slabs(block)
            confidence = 80.0 if orientation else 65.0
            label = orientation or "sans-orientation"
            multi_floor = len(bands) > 1

            for floor_index, (bottom, top) in enumerate(bands):
                height = top - bottom
                if not (MIN_WALL_HEIGHT <= height <= MAX_WALL_HEIGHT):
                    logger.info(
                        "Bande d'étage implausible (%.2f m) sur le bloc %s de %s : ignorée",
                        height, label, self.dxf_path)
                    continue

                walls.append(DetectedWall(
                    name=("Mur façade %s (étage %d)" % (label, floor_index))
                         if multi_floor else "Mur façade %s" % label,
                    match_key="facade-%s" % label,
                    orientation=orientation,
                    layer=block.layer,
                    wall_type="exterior",
                    geometry_type="unknown",
                    length=block.width,
                    height=height,
                    # épaisseur et position en plan non observables en façade
                    thickness=None,
                    confidence=confidence,
                    detection_method="geometry",
                    floor_index=floor_index,
                ))

        if not walls:
            logger.warning(
                "Aucune bande d'étage plausible sur les blocs de façade de %s",
                self.dxf_path)
        return walls

    def _detect_elevation_fallback(self) -> List[DetectedWall]:
        """Repli quand aucun contour fermé n'est trouvé : emprise globale des
        segments, un seul mur, sans découpe par dalle (comportement
        d'origine, pour les plans dessinés en traits ouverts)."""
        ctx = self.context
        orientation = find_orientation(ctx.title, *self.collect_texts())
        box = self.segments_bounding_box(self.collect_segments(ELEVATION_SECTION_LAYERS))
        if not box:
            logger.warning("Aucune géométrie de mur trouvée sur la façade %s",
                           self.dxf_path)
            return []

        minx, miny, maxx, maxy = box
        height = maxy - miny
        length = maxx - minx
        if not (MIN_WALL_HEIGHT <= height <= MAX_WALL_HEIGHT):
            logger.warning("Hauteur de façade implausible (%.2f m) dans %s : ignorée",
                           height, self.dxf_path)
            return []

        label = orientation or "sans-orientation"
        return [DetectedWall(
            name="Mur façade %s" % label,
            match_key="facade-%s" % label,
            orientation=orientation,
            layer=None,
            wall_type="exterior",
            geometry_type="unknown",
            length=length,
            height=height,
            thickness=None,
            confidence=65.0 if orientation else 55.0,
            detection_method="geometry",
            floor_index=0,
        )]

    def _block_orientation(self, block: Outline,
                           label_texts: List[Tuple[str, float, float]]
                           ) -> Optional[str]:
        """Texte « FACADE NORD » le plus proche du centre du bloc, à
        distance plausible. Un texte trop loin appartient à un autre bloc."""
        if not label_texts:
            return None
        cx, cy = block.center
        best_text, best_distance = None, FACADE_LABEL_MAX_DISTANCE
        for text, x, y in label_texts:
            distance = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if distance < best_distance:
                best_text, best_distance = text, distance
        return find_orientation(best_text) if best_text else None

    def _split_block_by_slabs(self, block: Outline) -> List[Tuple[float, float]]:
        """Bandes verticales (bas, haut) du bloc, séparées par les dalles
        trouvées à l'intérieur. Sans dalle, une seule bande = le bloc entier."""
        slabs = self._find_slab_bands(block)
        bands, prev_top = [], block.miny
        for slab_bottom, slab_top in slabs:
            bands.append((prev_top, slab_bottom))
            prev_top = slab_top
        bands.append((prev_top, block.maxy))
        return bands

    def _find_slab_bands(self, block: Outline) -> List[Tuple[float, float]]:
        """Dalles de plancher à l'intérieur du bloc : deux traits horizontaux
        parallèles traversant (presque) toute sa largeur. Un linteau ou un
        appui de fenêtre est beaucoup plus court — c'est ce qui les distingue,
        bien plus que leur épaisseur."""
        pad = 0.5
        segments = [
            (line, layer) for line, layer in self.collect_segments(FACADE_DETAIL_LAYERS)
            if self._segment_in_bounds(
                line, block.minx - pad, block.miny - pad,
                block.maxx + pad, block.maxy + pad)
        ]
        if not segments:
            return []

        pairs = self.find_parallel_pairs(
            segments,
            min_width=SLAB_MIN_THICKNESS,
            max_width=SLAB_MAX_THICKNESS,
            min_length=block.width * SLAB_MIN_LENGTH_RATIO,
            angle_tolerance=SLAB_ANGLE_TOLERANCE,
        )

        bands = []
        for pair in pairs:
            angle = self.line_angle(pair.axis)
            if not (angle <= SLAB_ANGLE_TOLERANCE or angle >= 180 - SLAB_ANGLE_TOLERANCE):
                continue  # une dalle est horizontale ; on écarte les partitions verticales
            _, cy = pair.center
            if block.miny < cy < block.maxy:
                bands.append((cy - pair.width / 2.0, cy + pair.width / 2.0))

        return sorted(bands)

    @staticmethod
    def _segment_in_bounds(line: LineString, minx: float, miny: float,
                           maxx: float, maxy: float) -> bool:
        xs = [c[0] for c in line.coords]
        ys = [c[1] for c in line.coords]
        return (minx <= min(xs) and max(xs) <= maxx
                and miny <= min(ys) and max(ys) <= maxy)

    # ========================================================
    # VUE COUPE — hauteur (et épaisseur) du niveau
    # (aucun mur n'est localisable en plan : valeurs communes au niveau)
    # ========================================================

    def _detect_from_section_view(self) -> List[DetectedWall]:
        ctx = self.context
        heights, thicknesses = [], []

        for outline in self.collect_closed_outlines(ELEVATION_SECTION_LAYERS):
            if not (MIN_WALL_HEIGHT <= outline.height <= MAX_WALL_HEIGHT):
                continue
            heights.append(outline.height)
            if MIN_WALL_THICKNESS <= outline.width <= MAX_WALL_THICKNESS:
                thicknesses.append(outline.width)

        if not heights:
            box = self.segments_bounding_box(self.collect_segments(ELEVATION_SECTION_LAYERS))
            if not box:
                logger.warning("Aucune géométrie de mur trouvée sur la coupe %s",
                               self.dxf_path)
                return []
            height = box[3] - box[1]
            if not (MIN_WALL_HEIGHT <= height <= MAX_WALL_HEIGHT):
                logger.warning("Hauteur de coupe implausible (%.2f m) dans %s : ignorée",
                               height, self.dxf_path)
                return []
            heights = [height]

        return [DetectedWall(
            name="Murs %s (coupe)" % (ctx.level_label or "du niveau"),
            match_key=ctx.match_key(LEVEL_WILDCARD),
            geometry_type="unknown",
            height=median(heights),
            thickness=median(thicknesses) if thicknesses else None,
            confidence=70.0,
            detection_method="geometry",
        )]

    # --------------------------------------------------------
    # EXPORT
    # --------------------------------------------------------

    def export_json(self, walls: List[DetectedWall], output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([w.to_odoo_dict() for w in walls], f, ensure_ascii=False, indent=2)
        logger.info("Export JSON écrit : %s (%d murs)", output_path, len(walls))


# ============================================================
# CONSOLIDATION : COMPLÉTER LES MURS DÉJÀ CONNUS
# ============================================================

@dataclass
class WallMergePlan:
    """Résultat de la consolidation : ce qu'il reste à écrire côté Odoo.

    `updates` est une liste de (id du mur existant, valeurs à écrire) ne
    contenant QUE des champs jusque-là vides."""

    creates: List[dict]
    updates: List[Tuple[int, dict]]

    @property
    def is_empty(self) -> bool:
        return not self.creates and not self.updates


GEOMETRY_FIELDS = ("start_x", "start_y", "end_x", "end_y", "center_x", "center_y")


def has_axis(wall: dict) -> bool:
    """Un mur est localisé en plan si ses deux extrémités sont connues et
    distinctes. Une coordonnée nulle étant une position valable, c'est le seul
    critère fiable pour distinguer « à l'origine » de « non renseigné »."""
    start = (wall.get("start_x") or 0.0, wall.get("start_y") or 0.0)
    end = (wall.get("end_x") or 0.0, wall.get("end_y") or 0.0)
    return start != end


def is_empty_value(field: str, value) -> bool:
    """Un champ est « à compléter » s'il n'a jamais été observé sur aucune
    vue. Côté Odoo, un flottant non renseigné vaut 0.0 et une sélection non
    renseignée vaut « unknown »."""
    if value in (None, False, ""):
        return True
    if field in ("wall_type", "material", "geometry_type"):
        return value in EMPTY_SELECTION_VALUES
    if field in ("length", "thickness", "height", "confidence",
                 "start_x", "start_y", "end_x", "end_y", "center_x", "center_y"):
        return not value
    return False


def _fields_to_fill(existing: dict, detected: DetectedWall) -> dict:
    """Champs observés par cette vue et encore vides sur le mur existant.
    Le nom et la clé déjà posés ne sont jamais réécrits."""
    detected_vals = detected.to_odoo_vals()
    vals = {}
    for field, value in detected_vals.items():
        if field in ("name", "match_key", "confidence") or field in GEOMETRY_FIELDS:
            continue
        # Ni ce que la vue n'a pas observé, ni ce qui est déjà renseigné.
        if is_empty_value(field, value):
            continue
        if is_empty_value(field, existing.get(field)):
            vals[field] = value

    # La géométrie se complète en bloc : une coordonnée nulle est une position
    # valable, seule l'absence d'axe signale un mur pas encore localisé.
    if detected.has_axis and not has_axis(existing):
        vals.update({f: detected_vals[f] for f in GEOMETRY_FIELDS
                     if f in detected_vals})

    # La confiance reflète la meilleure observation faite sur ce mur.
    if detected.confidence > (existing.get("confidence") or 0.0):
        vals["confidence"] = detected.confidence

    # Un mur vu sous deux angles différents a été reconnu par deux méthodes.
    if vals and existing.get("detection_method") not in (None, "combined"):
        vals["detection_method"] = "combined"

    if not existing.get("match_key"):
        vals["match_key"] = detected.match_key

    return vals


def _axis_distance(existing: dict, detected: DetectedWall) -> Optional[float]:
    """Distance entre les axes de deux murs, ou None si l'un des deux n'a pas
    de géométrie en plan (cas d'un mur issu d'une façade ou d'une coupe)."""
    if not detected.has_axis or not has_axis(existing):
        return None
    try:
        a = LineString([(existing["start_x"], existing["start_y"]),
                        (existing["end_x"], existing["end_y"])])
        b = LineString([(detected.start_x, detected.start_y),
                        (detected.end_x, detected.end_y)])
    except Exception:
        return None
    return max(a.distance(b), a.hausdorff_distance(b) / 2.0)


def _match_score(existing: dict, detected: DetectedWall) -> Optional[float]:
    """Score de rapprochement entre un mur connu et un mur détecté, ou None
    s'ils ne désignent pas le même ouvrage.

    Deux rapprochements possibles, du plus sûr au plus faible :
      1. même clé d'identité (même niveau, même désignation)
      2. axes superposés dans le plan

    PAS de repli sur la seule orientation partagée : une orientation
    (nord/sud/est/ouest) est posée sur TOUS les murs extérieurs qualifiants
    d'une vue en plan (cf. `_assign_plan_orientations`), pas seulement sur le
    mur « titulaire » de la façade — un simple mur de refend proche du bord
    sud partage la même orientation que la vraie façade sud. Un repli sur ce
    seul critère rapprochait un mur de façade sans géométrie du premier mur
    venu de la même orientation, n'importe où dans le projet."""
    if existing.get("match_key") and existing["match_key"] == detected.match_key:
        return 100.0

    distance = _axis_distance(existing, detected)
    if distance is not None:
        if distance > SAME_WALL_TOLERANCE:
            return None
        return 90.0 - distance

    return None


def merge_detected_walls(
    existing_walls: Sequence[dict], detected_walls: Sequence[DetectedWall]
) -> WallMergePlan:
    """Consolide les murs détectés avec ceux déjà connus pour le même niveau.

    Règle unique : on ne remplit que le vide. Une valeur déjà observée sur une
    autre vue n'est jamais écrasée — c'est ce qui permet d'importer la façade
    puis la vue en plan (ou l'inverse) et d'obtenir un mur complet.

    `existing_walls` : dicts des murs en base (id + champs de construction.wall).
    """
    creates: List[dict] = []
    updates: List[Tuple[int, dict]] = []
    available = {w["id"]: w for w in existing_walls}

    level_wide = [w for w in detected_walls if w.is_level_wide]
    specific = [w for w in detected_walls if not w.is_level_wide]

    # 1. Murs désignant un ouvrage précis : appariement un pour un.
    for detected in specific:
        best_id, best_score = None, 0.0
        for wall_id, existing in available.items():
            score = _match_score(existing, detected)
            if score is not None and score > best_score:
                best_id, best_score = wall_id, score

        if best_id is None:
            creates.append(detected.to_odoo_vals())
            continue

        vals = _fields_to_fill(available.pop(best_id), detected)
        if vals:
            updates.append((best_id, vals))

    # 2. Murs décrivant tout le niveau (coupe) : ils complètent chaque mur
    #    connu du niveau, y compris ceux qui viennent d'être appariés.
    pending: Dict[int, dict] = dict(updates)
    for detected in level_wide:
        if not existing_walls:
            creates.append(detected.to_odoo_vals())
            continue
        for existing in existing_walls:
            already = pending.get(existing["id"], {})
            vals = _fields_to_fill({**existing, **already}, detected)
            if vals:
                pending.setdefault(existing["id"], {}).update(vals)

    return WallMergePlan(creates=creates, updates=list(pending.items()))


# ============================================================
# INTÉGRATION ODOO (XML-RPC)
# ============================================================

def push_walls_to_odoo(
    walls: List[DetectedWall],
    dwg_file_id: int,
    url: str,
    db: str,
    username: str,
    password: str,
):
    """Pousse les murs détectés dans Odoo via XML-RPC."""
    import xmlrpc.client

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, username, password, {})
    models_proxy = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    created_ids = []
    for wall in walls:
        vals = wall.to_odoo_vals()
        vals["dwg_file_id"] = dwg_file_id
        wall_id = models_proxy.execute_kw(
            db, uid, password,
            "construction.wall", "create",
            [vals],
        )
        created_ids.append(wall_id)

    logger.info("%d murs créés dans Odoo (dwg_file_id=%s)", len(created_ids), dwg_file_id)
    return created_ids


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Détection de murs dans un DXF")
    parser.add_argument("dxf_path", help="Chemin du fichier DXF à analyser")
    parser.add_argument("-o", "--output", default="murs_detectes.json",
                        help="Fichier JSON de sortie")
    parser.add_argument("-v", "--view", default="plan",
                        help="Type de vue du plan : plan, facade, coupe...")
    parser.add_argument("-n", "--level", default=None,
                        help="Niveau du plan : R+0, R+1, Sous-sol...")
    args = parser.parse_args()

    plan_context = PlanContext.build(
        view=args.view, level=args.level, level_label=args.level,
        title=args.dxf_path)
    service = WallDetectionService(args.dxf_path, context=plan_context)
    detected = service.detect_walls()
    service.export_json(detected, args.output)

    # Résumé console
    print(f"\n=== {len(detected)} murs détectés (vue {plan_context.view}) ===")
    for w in detected:
        def fmt(value, unit="m"):
            return f"{value:.2f}{unit}" if value is not None else "-"
        print(f"  [{w.layer or '-'}] {w.wall_type:9s} "
              f"L={fmt(w.length):>7s}  ép={fmt(w.thickness):>7s}  "
              f"h={fmt(w.height):>7s}  orient={w.orientation or '-':<6s} "
              f"conf={w.confidence:.0f}  clé={w.match_key}")
