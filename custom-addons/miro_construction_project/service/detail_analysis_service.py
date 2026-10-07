# -*- coding: utf-8 -*-
"""
detail_analysis_service.py
==========================

Lecture d'un plan de COUPES ET DÉTAILS (plan d'exécution).

Ce plan ne crée PAS d'ouvrage : ses coupes redessinent les dalles et les
murs déjà portés par les plans de coffrage, et ses détails sont des
agrandissements. Il apporte en revanche ce qu'aucune vue en plan ne montre,
la dimension verticale des ouvrages. Le service en tire un PROFIL
STRUCTUREL qui complète les brouillons des autres plans d'exécution :

  - coupes (calque S-NIV) : niveaux, hauteur libre de chaque étage
    (-> hauteur des poteaux et des murs), épaisseur de chaque plancher
    (S-DAL), section des semelles filantes (S-SEM-FIL) et longrines (S-LON) ;
  - détails « Dn - ... » à leur propre échelle (« Echelle 1:20ʺ) : section
    des semelles isolées (S-SEM), poteaux (S-POT), hauteur des poutres
    (S-POU), épaisseur des dalles (S-DAL) ;
  - tableau « FERRAILLAGE TYPE » et textes « Poutre : 4 HA14 ... » :
    ferraillage par type d'ouvrage ;
  - calque X-HYP et mentions « NON CONFORME » : anomalies à signaler.

L'échelle d'une coupe est calée sur ses repères de niveau (deux textes
« +0.00 » / « +2.80 » et leurs traits suffisent) : le service ne dépend donc
pas de l'unité déclarée dans le DXF. Un détail est ramené à l'échelle des
coupes par le rapport de leurs échelles (1:20 contre 1:50 du cartouche).
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    from .formwork_detection_service import ExecutionPlanReader, PlacedText
    from .plan_analysis import Outline, normalize_text
except ImportError:  # exécution directe du module en ligne de commande
    from formwork_detection_service import ExecutionPlanReader, PlacedText  # type: ignore
    from plan_analysis import Outline, normalize_text  # type: ignore

logger = logging.getLogger("detail_analysis_service")


# ============================================================
# CONFIGURATION
# ============================================================

LEVEL_LAYER = "S-NIV"
SLAB_LAYER = "S-DAL"
WARNING_LAYERS = ("X-HYP",)

# Valeur d'un repère de niveau : « +2.80 », « -0.15 TN », « ±0.00 »
LEVEL_PATTERN = re.compile(r"^\s*([+\-±]?\s*\d+(?:[.,]\d+)?)\b")
NATURAL_GROUND = re.compile(r"\bTN\b", re.I)

DETAIL_TITLE = re.compile(r"^\s*(D\s?\d+)\s*[-–:]\s*(.+)$", re.I)
VIEW_SCALE = re.compile(r"\b[ée]chelle\s*:?\s*1\s*[:/]\s*(\d+)", re.I)
SHEET_SCALE = re.compile(r"^\s*1\s*[:/]\s*(\d+)\s*$")
SECTIONS_SCALE = re.compile(r"\bcoupes?\s*1\s*[:/]\s*(\d+)", re.I)

# Ce qu'un détail montre, selon le calque : ouvrage et dimensions lues
# (« w » = étendue horizontale, « h » = étendue verticale du dessin).
DETAIL_READINGS = {
    "S-SEM": ("semelle", ("w", "h")),
    "S-POT": ("poteau", ("w",)),
    "S-POU": ("poutre", ("h",)),
    "S-LON": ("longrine", ("h",)),
    "S-DAL": ("dalle", ("h",)),
}
# Ouvrages coupés transversalement dans les coupes : la coupe en donne la
# section complète.
SECTION_READINGS = {
    "S-SEM-FIL": "semelle_filante",
    "S-LON": "longrine",
}

# Codes du tableau de ferraillage -> types d'ouvrage
REINFORCEMENT_CODES = {
    "DAL": ("dalle",),
    "LON": ("longrine",),
    "POT": ("poteau",),
    "POU": ("poutre",),
    "SEM": ("semelle", "semelle_filante"),
    "SEMF": ("semelle_filante",),
    "VOI": ("mur",),
}
REINFORCEMENT_PREFIXES = (
    ("semelle filante", "semelle_filante"),
    ("semelle", "semelle"),
    ("longrine", "longrine"),
    ("poutre", "poutre"),
    ("poteau", "poteau"),
    ("dalle", "dalle"),
    ("plancher", "dalle"),
    ("paillasse", "escalier"),
)
REBAR = re.compile(r"\b(HA\s?\d+|ST\s?\d+\w*|T\d+)\b", re.I)

# Garde-fous : une dimension hors de ces bornes trahit une échelle mal lue
PLAUSIBLE = {"w": (0.10, 3.00), "h": (0.05, 2.00)}
MAX_STOREY_HEIGHT = 6.0

# Ouvertures coupées dans les coupes, et leur repère : « F-N0-05 » =
# fenêtre, niveau 0, n° 05 ; P porte, PF porte-fenêtre, PG porte de garage,
# B baie libre.
OPENING_LAYERS = ("A-OUV-FEN", "A-OUV-PRT")
OPENING_MARK = re.compile(
    r"^\s*(PF|PG|P|F|B)[\s\-_]?(?:N(\d+)[\s\-_]?)?(\d+)\s*$", re.I)
OPENING_TYPES = {"F": "window", "P": "door", "PF": "french_window",
                 "PG": "garage_door", "B": "bay"}
# Écart max (unités du dessin) entre le haut d'une ouverture et son repère
OPENING_LABEL_OFFSET = 0.30
# Titre d'une coupe, et sa position dans le tableau « COUPES » (« Y = 2.20 »)
SECTION_NAME = re.compile(r"\bcoupe\s+([A-Z0-9]+\s*-\s*[A-Z0-9]+)", re.I)
CUT_NAME = re.compile(r"^\s*([A-Z0-9]+-[A-Z0-9]+)\s*$")
CUT_POSITION = re.compile(r"^\s*([XY])\s*=\s*(-?\d+(?:[.,]\d+)?)", re.I)

# Écart (en unités du dessin) entre un repère de niveau et son trait
LEVEL_TEXT_OFFSET = 0.30
# Marge autour des repères de niveau pour délimiter une coupe (en mètres) :
# les fondations descendent sous le niveau le plus bas.
SECTION_MARGIN = 1.50
# Contours voisins de moins de ça : même dessin de détail
CLUSTER_GAP = 0.05
TITLE_X_MARGIN = 2.5


@dataclass
class LevelMark:
    minx: float
    maxx: float
    y: float
    elevation: float
    natural_ground: bool


@dataclass
class SectionView:
    """Une coupe : ses repères de niveau et le calage altitude = a·y + b."""

    marks: List[LevelMark]
    a: float
    b: float
    name: Optional[str] = None      # « A-A », lu dans le titre « COUPE A-A »

    @property
    def minx(self):
        return min(m.minx for m in self.marks)

    @property
    def maxx(self):
        return max(m.maxx for m in self.marks)

    def contains(self, outline: Outline) -> bool:
        cx, cy = outline.center
        margin = SECTION_MARGIN / self.a
        ys = [m.y for m in self.marks]
        return (self.minx <= cx <= self.maxx
                and min(ys) - margin <= cy <= max(ys) + margin)

    def elevation(self, y: float) -> float:
        return self.a * y + self.b


class DetailAnalysisService(ExecutionPlanReader):

    def __init__(self, dxf_path: str, unit_scale: float = 1.0):
        super().__init__(dxf_path)
        self.unit_scale = unit_scale or 1.0
        self._placed_texts = None

    # --------------------------------------------------------
    # POINT D'ENTRÉE
    # --------------------------------------------------------

    def analyze(self) -> dict:
        sections = self._section_views()
        coupe_scale = (statistics.median(s.a for s in sections)
                       if sections else self.unit_scale)

        profile: Dict[str, object] = {"views": [], "sections": {}}
        slabs = self._section_slabs(sections)
        profile.update(self._storeys(slabs, sections))

        readings: Dict[str, Dict[str, List[float]]] = {}
        self._read_sections(sections, readings)
        self._read_details(sections, coupe_scale, readings, profile)
        for slab in slabs:
            readings.setdefault("dalle", {}).setdefault("h", []).append(slab[2])
        profile["sections"] = {
            type_code: {dim: self._mode(values) for dim, values in dims.items()}
            for type_code, dims in readings.items()}

        profile["openings"] = self._section_openings(sections, profile.get("storeys") or [])
        profile["reinforcement"] = self._reinforcement()
        profile["warnings"] = self._warnings()
        profile["views"][:0] = [{"kind": "coupe", "levels": sorted(
            {m.elevation for m in s.marks})} for s in sections]
        logger.info("Profil structurel : %s", json.dumps(profile, ensure_ascii=False))
        return profile

    def to_analysis_result(self, profile: dict) -> dict:
        return {"schema_version": 1, "elements": [], "profile": profile}

    # --------------------------------------------------------
    # COUPES : repères de niveau et calage vertical
    # --------------------------------------------------------

    def _level_marks(self) -> List[LevelMark]:
        lines = []
        for e in self.msp.query(f'LINE[layer=="{LEVEL_LAYER}"]'):
            (x1, y1), (x2, y2) = (e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)
            if abs(y1 - y2) < 1e-6 and abs(x2 - x1) > 1e-6:
                lines.append((min(x1, x2), max(x1, x2), y1))

        marks = []
        for text in self.placed_texts():
            if text.layer != LEVEL_LAYER:
                continue
            match = LEVEL_PATTERN.match(text.text)
            if not match:
                continue
            value = float(match.group(1).replace("±", "").replace(" ", "")
                          .replace(",", "."))
            best = None
            for minx, maxx, y in lines:
                dy = text.y - y
                if minx - 0.1 <= text.x <= maxx and -0.05 <= dy <= LEVEL_TEXT_OFFSET:
                    if best is None or dy < best[0]:
                        best = (dy, minx, maxx, y)
            if best:
                marks.append(LevelMark(best[1], best[2], best[3], value,
                                       bool(NATURAL_GROUND.search(text.text))))
        return marks

    def _section_views(self) -> List[SectionView]:
        """Regroupe les repères dont les traits se chevauchent : une coupe
        par groupe, calée par moindres carrés sur ses repères."""
        groups: List[List[LevelMark]] = []
        for mark in sorted(self._level_marks(), key=lambda m: m.minx):
            for group in groups:
                if mark.minx <= max(m.maxx for m in group) and mark.maxx >= min(m.minx for m in group):
                    group.append(mark)
                    break
            else:
                groups.append([mark])

        views = []
        for marks in groups:
            ys = [m.y for m in marks]
            zs = [m.elevation for m in marks]
            if len(set(round(y, 6) for y in ys)) < 2:
                continue
            my, mz = statistics.mean(ys), statistics.mean(zs)
            a = (sum((y - my) * (z - mz) for y, z in zip(ys, zs))
                 / sum((y - my) ** 2 for y in ys))
            if a <= 0:
                logger.warning("Repères de niveau incohérents : coupe ignorée")
                continue
            views.append(SectionView(marks, a, mz - a * my))
        logger.info("%d coupe(s) calée(s) sur leurs repères de niveau", len(views))
        return views

    # --------------------------------------------------------
    # OUVERTURES COUPÉES : hauteur, allège, nature, position
    # --------------------------------------------------------

    def _name_sections(self, sections: List[SectionView]) -> None:
        """« COUPE A-A » placé au-dessus de la coupe dont il couvre la largeur."""
        for text in self.placed_texts():
            match = SECTION_NAME.search(text.text)
            if not match:
                continue
            for view in sections:
                top = max(m.y for m in view.marks)
                if view.minx <= text.x <= view.maxx and top - 0.5 <= text.y <= top + 1.5:
                    view.name = re.sub(r"\s+", "", match.group(1).upper())
                    break

    def _cut_positions(self) -> Dict[str, Tuple[str, float]]:
        """{« A-A »: (« Y », 2.20)} lus dans le tableau des coupes : c'est ce
        qui situe une coupe sur le plan."""
        cuts = {}
        for text in self.placed_texts():
            name = CUT_NAME.match(text.text)
            if not name:
                continue
            for cell in self.same_row(text):
                pos = CUT_POSITION.match(cell.text)
                if pos:
                    cuts[name.group(1).upper()] = (
                        pos.group(1).upper(), float(pos.group(2).replace(",", ".")))
                    break
        return cuts

    def _section_openings(self, sections: List[SectionView], storeys) -> List[dict]:
        """Ouvertures coupées par les coupes. Pour chacune : repère, nature
        (selon le repère), étage, allège et hauteur (calées sur les repères
        de niveau), et sa position le long de la coupe depuis le nu
        extérieur gauche du bâtiment — avec la position de la coupe, c'est ce
        qui la retrouve sur le plan de coffrage."""
        if not sections:
            return []
        self._name_sections(sections)
        cuts = self._cut_positions()
        labels = [(t, OPENING_MARK.match(t.text)) for t in self.placed_texts()]
        labels = [(t, m) for t, m in labels if m]
        slabs = self.collect_closed_outlines([SLAB_LAYER])

        found, seen = [], set()
        for outline in self.collect_closed_outlines(list(OPENING_LAYERS)):
            view = next((v for v in sections if v.contains(outline)), None)
            if not view:
                continue
            faces = [o for o in slabs if view.contains(o)]
            left = min((o.minx for o in faces), default=view.minx)
            right = max((o.maxx for o in faces), default=view.maxx)
            cx = (outline.minx + outline.maxx) / 2.0
            near = [(t.y - outline.maxy, t, m) for t, m in labels
                    if abs(t.x - cx) <= max(outline.width, 0.6)
                    and 0 <= t.y - outline.maxy <= OPENING_LABEL_OFFSET]
            _gap, label, match = min(near, key=lambda n: n[0]) if near else (None, None, None)

            bottom = view.elevation(outline.miny)
            top = view.elevation(outline.maxy)
            storey = None
            if match and match.group(2) is not None:
                storey = next((s for s in storeys
                               if s.get("index") == int(match.group(2))), None)
            if storey is None:
                below = [s for s in storeys if s["floor"] <= bottom + 0.02]
                storey = max(below, key=lambda s: s["floor"]) if below else None
            if storey is None:
                continue

            mark = re.sub(r"\s+", "", label.text.upper()) if label else None
            key = mark or (view.name, round(cx, 2), round(bottom, 2))
            if key in seen:
                continue
            seen.add(key)
            cut = cuts.get(view.name or "")
            found.append({
                "mark": mark,
                "type": OPENING_TYPES.get(match.group(1).upper()) if match else None,
                "storey": storey["index"],
                "sill": round(max(bottom - storey["floor"], 0.0), 3),
                "height": round(top - bottom, 3),
                "section": view.name,
                "cut_axis": cut[0] if cut else None,
                "cut_value": cut[1] if cut else None,
                "offset": round((cx - left) * view.a, 3),
                "span": round((right - left) * view.a, 3),
            })
        logger.info("%d ouverture(s) lue(s) dans les coupes", len(found))
        return found

    def _section_slabs(self, sections: List[SectionView]) -> List[Tuple[float, float, float]]:
        """(altitude basse, altitude haute, épaisseur) de chaque plancher coupé."""
        slabs = {}
        for outline in self.collect_closed_outlines([SLAB_LAYER]):
            for view in sections:
                if view.contains(outline):
                    bottom = round(view.elevation(outline.miny), 2)
                    top = round(view.elevation(outline.maxy), 2)
                    slabs[(bottom, top)] = round(top - bottom, 3)
                    break
        return sorted((b, t, e) for (b, t), e in slabs.items())

    @staticmethod
    def _storeys(slabs, sections: List[SectionView]) -> dict:
        """Un étage par plancher porteur : du dessus d'un plancher à la
        sous-face du suivant. L'index 0 est l'étage dont le sol est le plus
        proche de ±0.00 (le rez-de-chaussée)."""
        storeys = []
        for (_b0, top, _e0), (bottom, top1, thickness) in zip(slabs, slabs[1:]):
            clear = round(bottom - top, 3)
            if 0 < clear <= MAX_STOREY_HEIGHT:
                storeys.append({"floor": top, "ceiling": bottom,
                                "clear_height": clear, "slab_thickness": thickness,
                                "slab_top": top1})
        if storeys:
            ground = min(range(len(storeys)), key=lambda i: abs(storeys[i]["floor"]))
            for i, storey in enumerate(storeys):
                storey["index"] = i - ground
        result = {"storeys": storeys}
        if slabs:
            result["ground_slab"] = {"top": slabs[0][1], "thickness": slabs[0][2]}
        marks = [m for s in sections for m in s.marks]
        if marks:
            result["top_elevation"] = max(m.elevation for m in marks)
            tn = [m.elevation for m in marks if m.natural_ground]
            if tn:
                result["natural_ground"] = tn[0]
        return result

    def _read_sections(self, sections, readings) -> None:
        """Section des ouvrages linéaires coupés (semelle filante, longrine),
        dessinés ouverts ou fermés : leur boîte englobante suffit."""
        for layer, type_code in SECTION_READINGS.items():
            for points, _closed in self._polylines(layer):
                box = self.bounding_box(points)
                if not box:
                    continue
                outline = Outline(*box, layer=layer, points=points)
                view = next((v for v in sections if v.contains(outline)), None)
                if view:
                    self._record(readings, type_code,
                                 {"w": outline.width * view.a, "h": outline.height * view.a})

    def _polylines(self, layer: str):
        for e in self.msp.query(f'LWPOLYLINE POLYLINE[layer=="{layer}"]'):
            found = self.polyline_points(e)
            if found and len(found[0]) >= 2:
                yield found

    # --------------------------------------------------------
    # DÉTAILS : dessins agrandis, à ramener à l'échelle réelle
    # --------------------------------------------------------

    def _sheet_scale(self) -> Optional[int]:
        texts = self.placed_texts()
        for text in texts:
            match = SECTIONS_SCALE.search(text.text)
            if match:
                return int(match.group(1))
        for label in (t for t in texts if normalize_text(t.text) == "echelle"):
            near = [t for t in texts if SHEET_SCALE.match(t.text)
                    and abs(t.x - label.x) < 1.0 and 0 < label.y - t.y < 1.0]
            if near:
                return int(SHEET_SCALE.match(near[0].text).group(1))
        return None

    def _detail_titles(self) -> List[Tuple[PlacedText, Optional[int]]]:
        texts = self.placed_texts()
        titles = []
        for text in texts:
            if not DETAIL_TITLE.match(text.text):
                continue
            scales = sorted(
                (abs(t.y - text.y) + abs(t.x - text.x), int(m.group(1)))
                for t in texts for m in [VIEW_SCALE.search(t.text)] if m
                and abs(t.x - text.x) < 1.0 and abs(t.y - text.y) < 0.8)
            titles.append((text, scales[0][1] if scales else None))
        return titles

    def _read_details(self, sections, coupe_scale, readings, profile) -> None:
        sheet_scale = self._sheet_scale()
        titles = self._detail_titles()
        if not titles:
            return
        if not sheet_scale:
            logger.warning("Échelle des coupes introuvable (cartouche) : les "
                           "détails ne sont pas mesurés")
            return

        outlines = [o for o in self.collect_closed_outlines(list(DETAIL_READINGS))
                    if not any(v.contains(o) for v in sections)]
        for cluster in self._clusters(outlines):
            box = (min(o.minx for o in cluster), min(o.miny for o in cluster),
                   max(o.maxx for o in cluster), max(o.maxy for o in cluster))
            title = self._title_for(box, titles)
            if not title or not title[1]:
                continue
            factor = coupe_scale * title[1] / sheet_scale
            profile["views"].append({"kind": "detail", "name": title[0].text,
                                     "scale": title[1]})
            for outline in cluster:
                type_code, dims = DETAIL_READINGS[outline.layer]
                measured = {"w": outline.width * factor, "h": outline.height * factor}
                self._record(readings, type_code, {d: measured[d] for d in dims})

    @staticmethod
    def _clusters(outlines: List[Outline]) -> List[List[Outline]]:
        def touch(a, b):
            return not (a.maxx + CLUSTER_GAP < b.minx or b.maxx + CLUSTER_GAP < a.minx
                        or a.maxy + CLUSTER_GAP < b.miny or b.maxy + CLUSTER_GAP < a.miny)

        clusters: List[List[Outline]] = []
        for outline in outlines:
            linked = [c for c in clusters if any(touch(outline, o) for o in c)]
            merged = [outline] + [o for c in linked for o in c]
            clusters = [c for c in clusters if c not in linked] + [merged]
        return clusters

    @staticmethod
    def _title_for(box, titles):
        """Titre d'un dessin de détail : le plus proche verticalement parmi
        ceux qui sont au-dessus ou au-dessous, dans son alignement."""
        minx, miny, maxx, maxy = box
        best, best_gap = None, None
        for title, scale in titles:
            if not (minx - TITLE_X_MARGIN <= title.x <= maxx + TITLE_X_MARGIN):
                continue
            if miny <= title.y <= maxy:
                continue
            gap = miny - title.y if title.y < miny else title.y - maxy
            if best_gap is None or gap < best_gap:
                best, best_gap = (title, scale), gap
        return best

    @staticmethod
    def _record(readings, type_code, dims) -> None:
        for dim, value in dims.items():
            low, high = PLAUSIBLE[dim]
            if low <= value <= high:
                readings.setdefault(type_code, {}).setdefault(dim, []).append(value)
            else:
                logger.info("%s %s = %.3f m hors bornes : ignoré", type_code, dim, value)

    @staticmethod
    def _mode(values: List[float]) -> float:
        """Valeur la plus fréquente, au centimètre : un ouvrage vu dans
        plusieurs coupes et détails doit donner la même section."""
        return Counter(round(v, 2) for v in values).most_common(1)[0][0]

    # --------------------------------------------------------
    # FERRAILLAGE ET ANOMALIES
    # --------------------------------------------------------

    def _reinforcement(self) -> Dict[str, str]:
        found: Dict[str, str] = {}
        # 1. Tableau : code d'ouvrage en tête de ligne, armatures à droite
        for text in self.placed_texts():
            types = REINFORCEMENT_CODES.get(text.text.strip().upper())
            if not types:
                continue
            cells = [t.text for t in sorted(self.same_row(text), key=lambda t: t.x)
                     if t.x > text.x and REBAR.search(t.text)]
            for type_code in types:
                if cells:
                    found.setdefault(type_code, " ; ".join(cells))
        # 2. Légendes de détail : « Poutre : 4 HA14 + cadres HA6 e=15 »
        for text in self.placed_texts():
            head, sep, tail = text.text.partition(":")
            if not sep or not REBAR.search(tail):
                continue
            head = normalize_text(head)
            for keyword, type_code in REINFORCEMENT_PREFIXES:
                if keyword in head:
                    found.setdefault(type_code, tail.strip())
                    break
        return found

    def _warnings(self) -> List[str]:
        seen, warnings = set(), []
        for text in self.placed_texts():
            norm = normalize_text(text.text)
            if text.layer not in WARNING_LAYERS and "non conforme" not in norm:
                continue
            body = re.sub(r"^(non conforme\s*:?\s*|-\s*)", "", norm).strip(" -:")
            if len(body) < 5:
                continue  # titre seul (« NON CONFORME : »), détail à la ligne
            key = re.sub(r"^(non conforme\s*:?\s*)", "", body).strip(" -:")
            if key not in seen:
                seen.add(key)
                warnings.append(text.text.strip(" -"))
        # Ligne de détail d'un tableau, sous un titre « NON CONFORME : »
        for text in self.placed_texts():
            if normalize_text(text.text).strip(" :") != "non conforme":
                continue
            for line in self.placed_texts():
                dy = text.y - line.y
                if abs(line.x - text.x) < 0.5 and 0 < dy < 3 * max(text.height, 0.05):
                    body = normalize_text(line.text).strip(" -:")
                    if body and body not in seen and len(body) >= 5:
                        seen.add(body)
                        warnings.append("NON CONFORME : " + line.text.strip(" -"))
        return warnings


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Profil structurel d'un plan de détails")
    parser.add_argument("dxf_path")
    parser.add_argument("-s", "--scale", type=float, default=1.0)
    args = parser.parse_args()
    result = DetailAnalysisService(args.dxf_path, unit_scale=args.scale).analyze()
    print(json.dumps(result, ensure_ascii=False, indent=2))
