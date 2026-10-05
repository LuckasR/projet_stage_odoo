
# -*- coding: utf-8 -*-
"""
wall_detection_service.py
=========================

Service de détection automatique des murs dans un fichier DXF/DWG.

Optimisations de performance :
    - Indexation spatiale (shapely.strtree.STRtree) pour la recherche
      de paires de lignes parallèles : on ne compare plus chaque ligne
      à TOUTES les autres (O(n²)) mais uniquement à ses voisines
      géométriques (recherche par bounding-box élargie).
    - Même principe pour la fusion des murs colinéaires
      (_merge_colinear_walls) : recherche des segments contributeurs
      via l'index plutôt qu'un balayage complet.
    - Pré-calcul des angles de lignes une seule fois.
    - Filtrage précoce par longueur minimale avant indexation.

Dépendances :
    pip install ezdxf shapely

Utilisation :
    service = WallDetectionService("plan.dxf")
    walls = service.detect_walls()
    service.export_json(walls, "murs_detectes.json")
"""

from __future__ import annotations

import json
import math
import logging
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict

import ezdxf
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import unary_union, linemerge
from shapely.strtree import STRtree

logger = logging.getLogger("wall_detection_service")
logging.basicConfig(level=logging.INFO)


# ============================================================
# CONFIGURATION
# ============================================================

WALL_LAYER_KEYWORDS = [
    "mur", "murs", "wall", "walls", "a-wall", "cloture",
    "cloison", "cloisons", "partition", "voile", "beton",
]

MIN_WALL_THICKNESS = 0.05
MAX_WALL_THICKNESS = 0.80
MIN_WALL_LENGTH = 0.30
PARALLEL_ANGLE_TOLERANCE = 2.0
COLINEAR_MERGE_TOLERANCE = 0.02
DEFAULT_WALL_HEIGHT = 2.50


# ============================================================
# STRUCTURE DE DONNÉES
# ============================================================

@dataclass
class DetectedWall:
    name: str
    layer: Optional[str] = None
    wall_type: str = "unknown"
    material: str = "unknown"
    geometry_type: str = "unknown"
    start_x: float = 0.0
    start_y: float = 0.0
    end_x: float = 0.0
    end_y: float = 0.0
    center_x: float = 0.0
    center_y: float = 0.0
    points: Optional[str] = None
    length: float = 0.0
    thickness: float = 0.0
    height: float = DEFAULT_WALL_HEIGHT
    confidence: float = 0.0
    detection_method: str = "geometry"

    def to_dict(self) -> dict:
        """Retourne la représentation dictionnaire du mur."""
        return asdict(self)


# ============================================================
# SERVICE PRINCIPAL
# ============================================================

class WallDetectionService:

    def __init__(self, dxf_path: str):
        self.dxf_path = dxf_path
        self.doc = ezdxf.readfile(dxf_path)
        self.msp = self.doc.modelspace()
        self._wall_counter = 0

    # --------------------------------------------------------
    # POINT D'ENTRÉE
    # --------------------------------------------------------

    def detect_walls(self) -> List[DetectedWall]:
        logger.info("Démarrage de la détection sur %s", self.dxf_path)

        candidate_lines = self._collect_lines()
        candidate_polylines = self._collect_polylines()
        hatch_polygons = self._collect_hatches()
        dimension_values = self._collect_dimensions()

        walls: List[DetectedWall] = []

        walls += self._detect_from_parallel_lines(candidate_lines)
        walls += self._detect_from_closed_polylines(candidate_polylines)

        self._cross_validate_with_hatches(walls, hatch_polygons)
        self._cross_validate_with_dimensions(walls, dimension_values)

        walls = self._merge_colinear_walls(walls)
        walls = self._filter_plausible_walls(walls)

        logger.info("Détection terminée : %d murs retenus", len(walls))
        return walls

    # --------------------------------------------------------
    # COLLECTE DES ENTITÉS BRUTES
    # --------------------------------------------------------

    def _is_wall_layer(self, layer_name: str) -> bool:
        layer_lower = (layer_name or "").lower()
        return any(kw in layer_lower for kw in WALL_LAYER_KEYWORDS)

    def _collect_lines(self) -> List[Tuple[LineString, str]]:
        result = []
        for e in self.msp.query("LINE"):
            start = (e.dxf.start.x, e.dxf.start.y)
            end = (e.dxf.end.x, e.dxf.end.y)
            if start == end:
                continue
            line = LineString([start, end])
            if line.length < MIN_WALL_LENGTH:
                # filtrage précoce : évite d'indexer des segments trop
                # courts pour être un mur (bruit, hachures, symboles)
                continue
            result.append((line, e.dxf.layer))
        return result

    def _collect_polylines(self) -> List[Tuple[Polygon, str, list]]:
        result = []
        for e in list(self.msp.query("LWPOLYLINE")) + list(self.msp.query("POLYLINE")):
            try:
                points = [(p[0], p[1]) for p in e.get_points()] if e.dxftype() == "LWPOLYLINE" \
                    else [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                closed = e.closed if hasattr(e, "closed") else e.is_closed
                if not closed or len(points) < 3:
                    continue
                poly = Polygon(points)
                if not poly.is_valid or poly.area <= 0:
                    continue
                result.append((poly, e.dxf.layer, points))
            except Exception as exc:
                logger.debug("Polyligne ignorée (%s) : %s", e, exc)
        return result

    def _collect_hatches(self) -> List[Tuple[Polygon, str]]:
        result = []
        for e in self.msp.query("HATCH"):
            try:
                for path in e.paths:
                    pts = [(v[0], v[1]) for v in path.vertices] if hasattr(path, "vertices") else []
                    if len(pts) >= 3:
                        poly = Polygon(pts)
                        if poly.is_valid and poly.area > 0:
                            result.append((poly, e.dxf.layer))
            except Exception as exc:
                logger.debug("Hatch ignoré : %s", exc)
        return result

    def _collect_dimensions(self) -> List[Tuple[float, Point]]:
        result = []
        for e in self.msp.query("DIMENSION"):
            try:
                text = e.dxf.text or e.get_measurement()
                value = float(str(text).replace(",", ".").strip())
                pos = e.dxf.text_midpoint if hasattr(e.dxf, "text_midpoint") else e.dxf.defpoint
                result.append((value, Point(pos.x, pos.y)))
            except Exception:
                continue
        return result

    # --------------------------------------------------------
    # STRATÉGIE 1 — PAIRES DE LIGNES PARALLÈLES (indexée)
    # --------------------------------------------------------

    def _line_angle(self, line: LineString) -> float:
        (x1, y1), (x2, y2) = line.coords[0], line.coords[-1]
        return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180

    def _detect_from_parallel_lines(
        self, lines: List[Tuple[LineString, str]]
    ) -> List[DetectedWall]:
        walls: List[DetectedWall] = []
        if not lines:
            return walls

        n = len(lines)
        geoms = [ln for ln, _ in lines]
        layers = [ly for _, ly in lines]

        # Pré-calcul des angles une seule fois
        angles: List[float] = [self._line_angle(g) for g in geoms]

        # Index spatial : chaque ligne est élargie (buffer) de l'épaisseur
        # max plausible d'un mur, ce qui permet de ne récupérer que les
        # voisines réellement candidates au lieu de tout comparer.
        buffered = [g.buffer(MAX_WALL_THICKNESS) for g in geoms]
        tree = STRtree(buffered)

        used = set()

        for i in range(n):
            if i in used or geoms[i].length < MIN_WALL_LENGTH:
                continue
            line_a = geoms[i]
            angle_a = angles[i]

            # Requête spatiale
            candidate_idx = tree.query(buffered[i])

            best_match = None
            best_distance = None

            for j in candidate_idx:
                j = int(j)
                if j == i or j in used:
                    continue
                angle_b = angles[j]
                angle_diff = min(abs(angle_a - angle_b), 180 - abs(angle_a - angle_b))
                if angle_diff > PARALLEL_ANGLE_TOLERANCE:
                    continue

                line_b = geoms[j]
                distance = line_a.distance(line_b)
                if not (MIN_WALL_THICKNESS <= distance <= MAX_WALL_THICKNESS):
                    continue

                overlap_ratio = self._overlap_ratio(line_a, line_b)
                if overlap_ratio < 0.5:
                    continue

                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_match = (j, line_b, layers[j])

            if best_match:
                j, line_b, layer_b = best_match
                layer_a = layers[i]
                used.add(i)
                used.add(j)

                axis = self._center_axis(line_a, line_b)
                layer = layer_a if self._is_wall_layer(layer_a) else layer_b

                confidence = 60.0
                method = "geometry"
                if self._is_wall_layer(layer_a) or self._is_wall_layer(layer_b):
                    confidence += 30.0
                    method = "combined" if method == "geometry" else "layer"

                self._wall_counter += 1
                (sx, sy), (ex, ey) = axis.coords[0], axis.coords[-1]
                walls.append(DetectedWall(
                    name=f"Mur {self._wall_counter} ({layer or 'sans calque'})",
                    layer=layer,
                    geometry_type="line_pair",
                    start_x=sx, start_y=sy,
                    end_x=ex, end_y=ey,
                    center_x=(sx + ex) / 2, center_y=(sy + ey) / 2,
                    length=axis.length,
                    thickness=best_distance,
                    height=DEFAULT_WALL_HEIGHT,
                    confidence=min(confidence, 95.0),
                    detection_method=method,
                ))

        return walls

    def _overlap_ratio(self, line_a: LineString, line_b: LineString) -> float:
        proj = [line_a.project(Point(c)) for c in line_b.coords]
        lo, hi = max(0, min(proj)), min(line_a.length, max(proj))
        overlap = max(0, hi - lo)
        shortest = min(line_a.length, line_b.length)
        return overlap / shortest if shortest > 0 else 0

    def _center_axis(self, line_a: LineString, line_b: LineString) -> LineString:
        a1, a2 = line_a.coords[0], line_a.coords[-1]
        b_proj1 = line_b.interpolate(line_b.project(Point(a1)))
        b_proj2 = line_b.interpolate(line_b.project(Point(a2)))
        mid1 = ((a1[0] + b_proj1.x) / 2, (a1[1] + b_proj1.y) / 2)
        mid2 = ((a2[0] + b_proj2.x) / 2, (a2[1] + b_proj2.y) / 2)
        return LineString([mid1, mid2])

    # --------------------------------------------------------
    # STRATÉGIE 2 — POLYLIGNES FERMÉES
    # --------------------------------------------------------

    def _detect_from_closed_polylines(
        self, polylines: List[Tuple[Polygon, str, list]]
    ) -> List[DetectedWall]:
        walls = []
        for poly, layer, raw_points in polylines:
            minx, miny, maxx, maxy = poly.bounds
            length_estimate = max(maxx - minx, maxy - miny)
            if length_estimate <= 0:
                continue
            thickness_estimate = poly.area / length_estimate

            if not (MIN_WALL_THICKNESS <= thickness_estimate <= MAX_WALL_THICKNESS):
                continue
            if length_estimate < MIN_WALL_LENGTH:
                continue

            confidence = 55.0
            method = "geometry"
            if self._is_wall_layer(layer):
                confidence += 30.0
                method = "combined"

            centroid = poly.centroid
            self._wall_counter += 1
            walls.append(DetectedWall(
                name=f"Mur {self._wall_counter} ({layer or 'sans calque'})",
                layer=layer,
                geometry_type="polygon",
                center_x=centroid.x, center_y=centroid.y,
                points=json.dumps(raw_points),
                length=length_estimate,
                thickness=thickness_estimate,
                height=DEFAULT_WALL_HEIGHT,
                confidence=min(confidence, 95.0),
                detection_method=method,
            ))
        return walls

    # --------------------------------------------------------
    # STRATÉGIE 3 — VALIDATION CROISÉE (HATCH + DIMENSION), indexée
    # --------------------------------------------------------

    def _cross_validate_with_hatches(
        self, walls: List[DetectedWall], hatch_polygons: List[Tuple[Polygon, str]]
    ) -> None:
        if not walls or not hatch_polygons:
            return
        polys = [p for p, _ in hatch_polygons]
        tree = STRtree(polys)
        for wall in walls:
            wall_point = Point(wall.center_x, wall.center_y)
            search_area = wall_point.buffer(0.05)
            for idx in tree.query(search_area):
                poly = polys[int(idx)]
                if poly.contains(wall_point) or poly.distance(wall_point) < 0.05:
                    wall.confidence = min(wall.confidence + 10.0, 99.0)
                    if wall.detection_method == "geometry":
                        wall.detection_method = "combined"
                    break

    def _cross_validate_with_dimensions(
        self, walls: List[DetectedWall], dimensions: List[Tuple[float, Point]]
    ) -> None:
        if not walls or not dimensions:
            return
        points = [p for _, p in dimensions]
        values = [v for v, _ in dimensions]
        tree = STRtree(points)
        for wall in walls:
            wall_point = Point(wall.center_x, wall.center_y)
            radius = max(wall.length, 1.0)
            search_area = wall_point.buffer(radius)
            for idx in tree.query(search_area):
                idx = int(idx)
                value, pos = values[idx], points[idx]
                if wall_point.distance(pos) < radius and abs(value - wall.thickness) < 0.02:
                    wall.confidence = min(wall.confidence + 5.0, 99.0)

    # --------------------------------------------------------
    # STRATÉGIE 4 — RECONSTRUCTION TOPOLOGIQUE (indexée)
    # --------------------------------------------------------

    def _merge_colinear_walls(self, walls: List[DetectedWall]) -> List[DetectedWall]:
        line_walls = [w for w in walls if w.geometry_type == "line_pair"]
        other_walls = [w for w in walls if w.geometry_type != "line_pair"]

        segments = [
            LineString([(w.start_x, w.start_y), (w.end_x, w.end_y)])
            for w in line_walls
        ]
        if not segments:
            return walls

        merged = linemerge(unary_union(segments))
        merged_lines = [merged] if merged.geom_type == "LineString" else list(merged.geoms)

        # Index spatial des segments d'origine pour retrouver rapidement
        # les contributeurs de chaque segment fusionné.
        seg_tree = STRtree(segments)

        result = []
        for merged_line in merged_lines:
            search_buffer = merged_line.buffer(COLINEAR_MERGE_TOLERANCE)
            candidate_idx = seg_tree.query(search_buffer)
            contributing = [
                line_walls[int(k)] for k in candidate_idx
                if search_buffer.contains(segments[int(k)])
            ]
            if not contributing:
                continue

            avg_thickness = sum(w.thickness for w in contributing) / len(contributing)
            best_layer = max(contributing, key=lambda w: w.confidence).layer
            avg_confidence = sum(w.confidence for w in contributing) / len(contributing)
            method = "combined" if any(w.detection_method == "combined" for w in contributing) else "geometry"

            (sx, sy), (ex, ey) = merged_line.coords[0], merged_line.coords[-1]
            self._wall_counter += 1
            result.append(DetectedWall(
                name=f"Mur {self._wall_counter} ({best_layer or 'sans calque'})",
                layer=best_layer,
                geometry_type="line_pair" if len(contributing) == 1 else "polyline",
                start_x=sx, start_y=sy, end_x=ex, end_y=ey,
                center_x=(sx + ex) / 2, center_y=(sy + ey) / 2,
                length=merged_line.length,
                thickness=avg_thickness,
                height=DEFAULT_WALL_HEIGHT,
                confidence=min(avg_confidence + (5.0 if len(contributing) > 1 else 0), 99.0),
                detection_method=method,
            ))

        return result + other_walls

    # --------------------------------------------------------
    # FILTRAGE FINAL
    # --------------------------------------------------------

    def _filter_plausible_walls(self, walls: List[DetectedWall]) -> List[DetectedWall]:
        return [
            w for w in walls
            if w.length >= MIN_WALL_LENGTH
            and MIN_WALL_THICKNESS <= w.thickness <= MAX_WALL_THICKNESS
        ]

    # --------------------------------------------------------
    # EXPORT
    # --------------------------------------------------------

    def export_json(self, walls: List[DetectedWall], output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([w.to_dict() for w in walls], f, ensure_ascii=False, indent=2)
        logger.info("Export JSON écrit : %s (%d murs)", output_path, len(walls))

    def export_csv(self, walls: List[DetectedWall], output_path: str) -> None:
        """Export optionnel au format CSV."""
        import csv
        if not walls:
            return
        fieldnames = list(walls[0].to_dict().keys())
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for w in walls:
                writer.writerow(w.to_dict())
        logger.info("Export CSV écrit : %s (%d murs)", output_path, len(walls))


# ============================================================
# CLI SIMPLE
# ============================================================

if __name__ == "__main__":
    import argparse
    import time          
 
    parser = argparse.ArgumentParser(description="Détection de murs dans un fichier DXF")
    parser.add_argument("dxf_path", help="Chemin du fichier DXF à analyser")
    parser.add_argument("-o", "--output", default="murs_detectes.json", help="Fichier JSON de sortie")
    parser.add_argument("--csv", default=None, help="Fichier CSV de sortie (optionnel)")
    args = parser.parse_args()

    t0 = time.time()
    service = WallDetectionService(args.dxf_path)
    detected_walls = service.detect_walls()
    service.export_json(detected_walls, args.output)
    if args.csv:
        service.export_csv(detected_walls, args.csv)
    logger.info("Temps total : %.2fs", time.time() - t0)