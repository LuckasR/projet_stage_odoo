# -*- coding: utf-8 -*-
"""
wall_viewer.py
================

Contrôleur Odoo exposant une page de visualisation des murs détectés
(construction.wall) pour un fichier DWG/DXF donné. Génère un SVG
interactif directement dans le navigateur, sans dépendance externe :
zoom/pan à la molette, couleurs par confiance, tooltips, filtres par
calque et par méthode de détection.

Route : GET /construction/walls/<int:dwg_file_id>
"""

import html as html_lib
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Marge autour du plan, en pourcentage de sa plus grande dimension
PADDING_RATIO = 0.08
CANVAS_SIZE = 1400  # taille de base du SVG en pixels (avant zoom utilisateur)


class ConstructionWallViewerController(http.Controller):

    @http.route(
        "/construction/walls/<int:dwg_file_id>",
        type="http",
        auth="user",
        website=False,
        csrf=False,
    )
    def wall_viewer(self, dwg_file_id, **kwargs):
        dwg_file = request.env["construction.dwg.files"].browse(dwg_file_id)
        if not dwg_file.exists():
            return request.not_found()

        # Les murs de ce plan, y compris ceux qu'il a seulement complétés
        # (mur né d'une vue en façade puis géolocalisé par cette vue en plan).
        walls = request.env["construction.wall"].search(
            ["|", ("dwg_file_id", "=", dwg_file_id),
                  ("source_file_ids", "in", dwg_file_id)]
        )

        wall_data = [self._wall_to_dict(w) for w in walls]
        html_page = self._render_page(dwg_file, wall_data)
        return request.make_response(
            html_page, headers=[("Content-Type", "text/html; charset=utf-8")]
        )

    # --------------------------------------------------------
    # PRÉPARATION DES DONNÉES
    # --------------------------------------------------------

    def _wall_to_dict(self, wall):
        return {
            "id": wall.id,
            "name": wall.name or "",
            "layer": wall.layer or "",
            "wall_type": wall.wall_type or "unknown",
            "geometry_type": wall.geometry_type or "unknown",
            "detection_method": wall.detection_method or "geometry",
            "start_x": wall.start_x,
            "start_y": wall.start_y,
            "end_x": wall.end_x,
            "end_y": wall.end_y,
            "center_x": wall.center_x,
            "center_y": wall.center_y,
            "length": round(wall.length, 3),
            "thickness": round(wall.thickness, 3),
            "confidence": round(wall.confidence, 1),
            "is_validated": wall.is_validated,
        }

    def _compute_bounds(self, wall_data):
        if not wall_data:
            return 0, 0, 10, 10

        xs, ys = [], []
        for w in wall_data:
            xs += [w["start_x"], w["end_x"], w["center_x"]]
            ys += [w["start_y"], w["end_y"], w["center_y"]]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        span_x = max(max_x - min_x, 0.01)
        span_y = max(max_y - min_y, 0.01)
        pad = max(span_x, span_y) * PADDING_RATIO

        return min_x - pad, min_y - pad, max_x + pad, max_y + pad

    # --------------------------------------------------------
    # GÉNÉRATION SVG + PAGE HTML
    # --------------------------------------------------------

    def _confidence_color(self, confidence):
        if confidence >= 80:
            return "#2e7d32"   # vert
        if confidence >= 60:
            return "#f57c00"   # orange
        return "#c62828"       # rouge

    def _build_svg_elements(self, wall_data, min_x, min_y, max_x, max_y):
        """Construit les éléments SVG. L'axe Y du DXF pointe vers le haut,
        celui du SVG vers le bas : on inverse Y lors de la projection."""
        span_x = max_x - min_x
        span_y = max_y - min_y
        scale = CANVAS_SIZE / max(span_x, span_y)

        def px(x):
            return (x - min_x) * scale

        def py(y):
            return (max_y - y) * scale  # inversion Y

        elements = []
        for w in wall_data:
            color = self._confidence_color(w["confidence"])
            stroke_width = max(w["thickness"] * scale, 1.5)
            validated_marker = " ✓" if w["is_validated"] else ""

            tooltip = (
                f"{html_lib.escape(w['name'])}{validated_marker}\n"
                f"Calque: {html_lib.escape(w['layer'] or '—')}\n"
                f"Longueur: {w['length']} m | Épaisseur: {w['thickness']} m\n"
                f"Confiance: {w['confidence']}% | Méthode: {w['detection_method']}"
            )

            elements.append(
                f'<g class="wall-group" '
                f'data-layer="{html_lib.escape(w["layer"])}" '
                f'data-method="{html_lib.escape(w["detection_method"])}" '
                f'data-confidence="{w["confidence"]}" '
                f'data-validated="{"1" if w["is_validated"] else "0"}">'
                f'<line x1="{px(w["start_x"]):.2f}" y1="{py(w["start_y"]):.2f}" '
                f'x2="{px(w["end_x"]):.2f}" y2="{py(w["end_y"]):.2f}" '
                f'stroke="{color}" stroke-width="{stroke_width:.2f}" '
                f'stroke-linecap="round" class="wall-line" data-id="{w["id"]}">'
                f'<title>{html_lib.escape(tooltip)}</title>'
                f'</line>'
                f'</g>'
            )
        return "\n".join(elements)

    def _render_page(self, dwg_file, wall_data):
        min_x, min_y, max_x, max_y = self._compute_bounds(wall_data)
        svg_elements = self._build_svg_elements(wall_data, min_x, min_y, max_x, max_y)

        layers = sorted({w["layer"] for w in wall_data if w["layer"]})
        methods = sorted({w["detection_method"] for w in wall_data})

        layer_options = "\n".join(
            f'<option value="{html_lib.escape(l)}">{html_lib.escape(l)}</option>' for l in layers
        )
        method_options = "\n".join(
            f'<option value="{html_lib.escape(m)}">{html_lib.escape(m)}</option>' for m in methods
        )

        stats = {
            "total": len(wall_data),
            "validated": sum(1 for w in wall_data if w["is_validated"]),
            "high_confidence": sum(1 for w in wall_data if w["confidence"] >= 80),
            "low_confidence": sum(1 for w in wall_data if w["confidence"] < 60),
        }

        title = html_lib.escape(dwg_file.filename or f"Fichier #{dwg_file.id}")

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<title>Murs détectés — {title}</title>
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
    .stat.green {{ background: #e8f5e9; color: #2e7d32; }}
    .stat.red {{ background: #ffebee; color: #c62828; }}
    #canvas-wrap {{
        position: absolute; top: 56px; left: 0; right: 0; bottom: 0;
        overflow: hidden; background: white; cursor: grab;
    }}
    #canvas-wrap.dragging {{ cursor: grabbing; }}
    svg {{ display: block; }}
    .wall-line {{ transition: opacity 0.15s; cursor: pointer; }}
    .wall-line:hover {{ opacity: 0.6; stroke: #1565c0 !important; }}
    .wall-group.hidden {{ display: none; }}
    #legend {{
        position: fixed; bottom: 16px; left: 16px; background: white;
        border: 1px solid #ddd; border-radius: 6px; padding: 10px 14px;
        font-size: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.1);
    }}
    #legend div {{ display: flex; align-items: center; gap: 6px; margin: 3px 0; }}
    #legend .swatch {{ width: 14px; height: 4px; border-radius: 2px; }}
</style>
</head>
<body>

<div id="toolbar">
    <h1>🧱 Murs — {title}</h1>
    <span class="stat">{stats['total']} murs</span>
    <span class="stat green">{stats['validated']} validés</span>
    <span class="stat green">{stats['high_confidence']} confiance ≥ 80%</span>
    <span class="stat red">{stats['low_confidence']} confiance &lt; 60%</span>

    <label>Calque :
        <select id="filter-layer">
            <option value="">Tous</option>
            {layer_options}
        </select>
    </label>

    <label>Méthode :
        <select id="filter-method">
            <option value="">Toutes</option>
            {method_options}
        </select>
    </label>

    <label><input type="checkbox" id="filter-low-confidence"/> Masquer confiance &lt; 60%</label>
    <label><input type="checkbox" id="filter-validated-only"/> Validés uniquement</label>

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
    <div><span class="swatch" style="background:#2e7d32"></span> Confiance ≥ 80%</div>
    <div><span class="swatch" style="background:#f57c00"></span> Confiance 60-80%</div>
    <div><span class="swatch" style="background:#c62828"></span> Confiance &lt; 60%</div>
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
    const layerSelect = document.getElementById('filter-layer');
    const methodSelect = document.getElementById('filter-method');
    const lowConfCheckbox = document.getElementById('filter-low-confidence');
    const validatedCheckbox = document.getElementById('filter-validated-only');

    function applyFilters() {{
        const layer = layerSelect.value;
        const method = methodSelect.value;
        const hideLowConf = lowConfCheckbox.checked;
        const validatedOnly = validatedCheckbox.checked;

        document.querySelectorAll('.wall-group').forEach(g => {{
            let visible = true;
            if (layer && g.dataset.layer !== layer) visible = false;
            if (method && g.dataset.method !== method) visible = false;
            if (hideLowConf && parseFloat(g.dataset.confidence) < 60) visible = false;
            if (validatedOnly && g.dataset.validated !== '1') visible = false;
            g.classList.toggle('hidden', !visible);
        }});
    }}

    [layerSelect, methodSelect, lowConfCheckbox, validatedCheckbox].forEach(el => {{
        el.addEventListener('change', applyFilters);
    }});
}})();
</script>

</body>
</html>"""