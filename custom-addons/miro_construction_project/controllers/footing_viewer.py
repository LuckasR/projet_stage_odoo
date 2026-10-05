# -*- coding: utf-8 -*-
"""
footing_viewer.py
==================

Contrôleur exposant une page de visualisation des éléments de fondation
validés (construction.element, générés depuis une analyse « footings ») pour
un plan DWG/DXF donné. Même principe que wall_viewer.py : un SVG interactif
généré côté serveur, sans dépendance externe.

Un ouvrage ponctuel (semelle, poteau) est dessiné comme un rectangle, sa
« zone source » (bbox relevée sur le plan) en donnant l'emprise directement.
Un ouvrage linéaire (semelle filante, longrine) est dessiné comme un trait :
sur ce plan, orthogonal, la diagonale de sa bbox EST le segment réel — c'est
la même propriété qui permettrait de reconstruire un mur à partir de sa seule
boîte englobante quand il est horizontal ou vertical.

Route : GET /construction/footings/<int:dwg_file_id>
"""

import html as html_lib
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

PADDING_RATIO = 0.08
CANVAS_SIZE = 1400

# Types dessinés comme un rectangle (ouvrage ponctuel) plutôt qu'un trait.
POINT_TYPES = ('semelle', 'poteau')

TYPE_COLORS = {
    'semelle': '#1565c0',
    'poteau': '#6a1b9a',
    'semelle_filante': '#2e7d32',
    'longrine': '#e65100',
}
DEFAULT_COLOR = '#455a64'


class ConstructionFootingViewerController(http.Controller):

    @http.route(
        "/construction/footings/<int:dwg_file_id>",
        type="http",
        auth="user",
        website=False,
        csrf=False,
    )
    def footing_viewer(self, dwg_file_id, **kwargs):
        dwg_file = request.env["construction.dwg.files"].browse(dwg_file_id)
        if not dwg_file.exists():
            return request.not_found()

        # Seuls les éléments VALIDÉS (état "generated") existent en tant que
        # construction.element : un brouillon encore en attente n'a pas
        # d'élément et ne peut donc pas être positionné ici. C'est voulu —
        # ce visualiseur montre ce qui a été retenu, pas ce qui est proposé.
        elements = request.env["construction.element"].search([
            ("source_file_id", "=", dwg_file_id),
        ])

        element_data = [self._element_to_dict(e) for e in elements
                        if e.source_bbox and len(e.source_bbox) == 4]
        html_page = self._render_page(dwg_file, element_data, len(elements))
        return request.make_response(
            html_page, headers=[("Content-Type", "text/html; charset=utf-8")]
        )

    # --------------------------------------------------------
    # PRÉPARATION DES DONNÉES
    # --------------------------------------------------------

    def _element_to_dict(self, element):
        minx, miny, maxx, maxy = element.source_bbox
        return {
            "id": element.id,
            "key": element.key or element.name,
            "type_code": element.element_type_id.code or "",
            "type_name": element.element_type_id.name or "",
            "level": element.level_id.name or "",
            "minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy,
            "dim_l": round(element.dim_l, 3),
            "dim_w": round(element.dim_w, 3),
            "dim_h": round(element.dim_h, 3),
            "qty_beton_m3": round(element.qty_beton_m3, 3),
            "qty_acier_kg": round(element.qty_acier_kg, 1),
            "qty_coffrage_m2": round(element.qty_coffrage_m2, 3),
            "confidence": round(element.confidence * 100, 0),
            "has_missing_fields": element.has_missing_fields,
        }

    def _compute_bounds(self, element_data):
        if not element_data:
            return 0, 0, 10, 10

        xs, ys = [], []
        for e in element_data:
            xs += [e["minx"], e["maxx"]]
            ys += [e["miny"], e["maxy"]]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        span_x = max(max_x - min_x, 0.01)
        span_y = max(max_y - min_y, 0.01)
        pad = max(span_x, span_y) * PADDING_RATIO

        return min_x - pad, min_y - pad, max_x + pad, max_y + pad

    # --------------------------------------------------------
    # GÉNÉRATION SVG + PAGE HTML
    # --------------------------------------------------------

    def _build_svg_elements(self, element_data, min_x, min_y, max_x, max_y):
        span_x = max_x - min_x
        span_y = max_y - min_y
        scale = CANVAS_SIZE / max(span_x, span_y)

        def px(x):
            return (x - min_x) * scale

        def py(y):
            return (max_y - y) * scale  # DXF: Y vers le haut ; SVG: Y vers le bas

        parts = []
        for e in element_data:
            color = TYPE_COLORS.get(e["type_code"], DEFAULT_COLOR)
            missing_marker = " ⚠" if e["has_missing_fields"] else ""
            tooltip = (
                f"{html_lib.escape(e['key'])}{missing_marker}\n"
                f"{html_lib.escape(e['type_name'])} — {html_lib.escape(e['level'] or '—')}\n"
                f"L={e['dim_l']} m  l={e['dim_w']} m  h={e['dim_h']} m\n"
                f"Béton {e['qty_beton_m3']} m³ | Acier {e['qty_acier_kg']} kg | "
                f"Coffrage {e['qty_coffrage_m2']} m²"
            )
            group_attrs = (
                f'data-type="{html_lib.escape(e["type_code"])}" '
                f'data-level="{html_lib.escape(e["level"])}" '
                f'data-missing="{"1" if e["has_missing_fields"] else "0"}"'
            )

            if e["type_code"] in POINT_TYPES:
                x, y = px(e["minx"]), py(e["maxy"])
                w = max(px(e["maxx"]) - px(e["minx"]), 2)
                h = max(py(e["miny"]) - py(e["maxy"]), 2)
                shape = (
                    f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                    f'fill="{color}" fill-opacity="0.35" stroke="{color}" '
                    f'stroke-width="1.5" class="footing-shape" data-id="{e["id"]}">'
                    f'<title>{html_lib.escape(tooltip)}</title></rect>'
                )
            else:
                stroke_width = max(e["dim_w"] * scale, 2)
                shape = (
                    f'<line x1="{px(e["minx"]):.2f}" y1="{py(e["miny"]):.2f}" '
                    f'x2="{px(e["maxx"]):.2f}" y2="{py(e["maxy"]):.2f}" '
                    f'stroke="{color}" stroke-width="{stroke_width:.2f}" '
                    f'stroke-linecap="round" class="footing-shape" data-id="{e["id"]}">'
                    f'<title>{html_lib.escape(tooltip)}</title></line>'
                )

            parts.append(f'<g class="footing-group" {group_attrs}>{shape}</g>')
        return "\n".join(parts)

    def _render_page(self, dwg_file, element_data, total_elements):
        min_x, min_y, max_x, max_y = self._compute_bounds(element_data)
        svg_elements = self._build_svg_elements(element_data, min_x, min_y, max_x, max_y)

        types = sorted({e["type_code"] for e in element_data if e["type_code"]})
        levels = sorted({e["level"] for e in element_data if e["level"]})

        type_options = "\n".join(
            f'<option value="{html_lib.escape(t)}">{html_lib.escape(t)}</option>' for t in types
        )
        level_options = "\n".join(
            f'<option value="{html_lib.escape(l)}">{html_lib.escape(l)}</option>' for l in levels
        )

        stats = {
            "total": total_elements,
            "shown": len(element_data),
            "beton": round(sum(e["qty_beton_m3"] for e in element_data), 2),
            "missing": sum(1 for e in element_data if e["has_missing_fields"]),
        }
        legend_items = "".join(
            f'<div><span class="swatch" style="background:{color}"></span> {html_lib.escape(code)}</div>'
            for code, color in TYPE_COLORS.items() if code in types
        )

        title = html_lib.escape(dwg_file.filename or f"Fichier #{dwg_file.id}")

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<title>Éléments de fondation — {title}</title>
<style>
    html, body {{ margin: 0; padding: 0; height: 100%; font-family: -apple-system, "Segoe UI", sans-serif; background: #f4f4f4; }}
    #toolbar {{
        position: fixed; top: 0; left: 0; right: 0; z-index: 10;
        background: white; border-bottom: 1px solid #ddd; padding: 10px 16px;
        display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }}
    #toolbar h1 {{ font-size: 15px; margin: 0; color: #333; font-weight: 600; }}
    #toolbar label {{ font-size: 12px; color: #555; display: flex; align-items: center; gap: 4px; }}
    #toolbar select {{ font-size: 12px; padding: 3px 6px; }}
    .stat {{ font-size: 12px; padding: 3px 9px; border-radius: 10px; background: #eee; color: #333; }}
    .stat.blue {{ background: #e3f2fd; color: #1565c0; }}
    .stat.red {{ background: #ffebee; color: #c62828; }}
    #canvas-wrap {{
        position: absolute; top: 56px; left: 0; right: 0; bottom: 0;
        overflow: hidden; background: white; cursor: grab;
    }}
    #canvas-wrap.dragging {{ cursor: grabbing; }}
    svg {{ display: block; }}
    .footing-shape {{ transition: opacity 0.15s; cursor: pointer; }}
    .footing-shape:hover {{ opacity: 0.65; }}
    .footing-group.hidden {{ display: none; }}
    #legend {{
        position: fixed; bottom: 16px; left: 16px; background: white;
        border: 1px solid #ddd; border-radius: 6px; padding: 10px 14px;
        font-size: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.1);
    }}
    #legend div {{ display: flex; align-items: center; gap: 6px; margin: 3px 0; }}
    #legend .swatch {{ width: 14px; height: 10px; border-radius: 2px; }}
</style>
</head>
<body>

<div id="toolbar">
    <h1>🏗️ Fondations — {title}</h1>
    <span class="stat">{stats['shown']} / {stats['total']} éléments</span>
    <span class="stat blue">{stats['beton']} m³ de béton</span>
    <span class="stat red">{stats['missing']} incomplet(s)</span>

    <label>Type :
        <select id="filter-type">
            <option value="">Tous</option>
            {type_options}
        </select>
    </label>

    <label>Niveau :
        <select id="filter-level">
            <option value="">Tous</option>
            {level_options}
        </select>
    </label>

    <label><input type="checkbox" id="filter-missing-only"/> Incomplets uniquement</label>

    <button id="reset-view" style="margin-left:auto; font-size:12px; padding:5px 10px; cursor:pointer;">
        Réinitialiser la vue
    </button>
</div>

<div id="canvas-wrap">
    <svg id="plan-svg" viewBox="0 0 {CANVAS_SIZE} {CANVAS_SIZE}" width="{CANVAS_SIZE}" height="{CANVAS_SIZE}">
        <g id="zoom-group">
            {svg_elements}
        </g>
    </svg>
</div>

<div id="legend">
    {legend_items}
</div>

<script>
(function() {{
    const svg = document.getElementById('plan-svg');
    const zoomGroup = document.getElementById('zoom-group');
    const wrap = document.getElementById('canvas-wrap');

    let scale = 1, offsetX = 0, offsetY = 0;
    let isDragging = false, lastX = 0, lastY = 0;

    function applyTransform() {{
        zoomGroup.setAttribute('transform', `translate(${{offsetX}},${{offsetY}}) scale(${{scale}})`);
    }}

    wrap.addEventListener('wheel', (e) => {{
        e.preventDefault();
        const rect = wrap.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const zoomFactor = e.deltaY < 0 ? 1.12 : 1 / 1.12;

        const worldX = (mouseX - offsetX) / scale;
        const worldY = (mouseY - offsetY) / scale;

        scale *= zoomFactor;
        scale = Math.min(Math.max(scale, 0.1), 40);

        offsetX = mouseX - worldX * scale;
        offsetY = mouseY - worldY * scale;
        applyTransform();
    }}, {{ passive: false }});

    wrap.addEventListener('mousedown', (e) => {{
        isDragging = true;
        lastX = e.clientX; lastY = e.clientY;
        wrap.classList.add('dragging');
    }});
    window.addEventListener('mousemove', (e) => {{
        if (!isDragging) return;
        offsetX += e.clientX - lastX;
        offsetY += e.clientY - lastY;
        lastX = e.clientX; lastY = e.clientY;
        applyTransform();
    }});
    window.addEventListener('mouseup', () => {{
        isDragging = false;
        wrap.classList.remove('dragging');
    }});

    document.getElementById('reset-view').addEventListener('click', () => {{
        scale = 1; offsetX = 0; offsetY = 0;
        applyTransform();
    }});

    // Filtres
    const typeSelect = document.getElementById('filter-type');
    const levelSelect = document.getElementById('filter-level');
    const missingCheckbox = document.getElementById('filter-missing-only');

    function applyFilters() {{
        const type = typeSelect.value;
        const level = levelSelect.value;
        const missingOnly = missingCheckbox.checked;

        document.querySelectorAll('.footing-group').forEach(g => {{
            let visible = true;
            if (type && g.dataset.type !== type) visible = false;
            if (level && g.dataset.level !== level) visible = false;
            if (missingOnly && g.dataset.missing !== '1') visible = false;
            g.classList.toggle('hidden', !visible);
        }});
    }}

    [typeSelect, levelSelect, missingCheckbox].forEach(el => {{
        el.addEventListener('change', applyFilters);
    }});
}})();
</script>

</body>
</html>"""
