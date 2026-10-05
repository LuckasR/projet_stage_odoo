# -*- coding: utf-8 -*-
"""
opening_viewer.py
=================

Page de visualisation des ouvertures (construction.opening) d'un plan :

    - Vue en plan  : les ouvertures localisées en plan, posées sur les murs
                     du même niveau (contexte en gris).
    - Élévations   : une façade par orientation, étages empilés ; chaque
                     ouverture est placée à sa position le long de la façade,
                     à son allège, avec sa largeur et sa hauteur. Une
                     ouverture dont la hauteur est encore inconnue (vue
                     seulement en plan) est dessinée en pointillés.

Le SVG est généré ici, en mètres (viewBox), sans dépendance externe :
zoom à la molette, déplacement à la souris, filtres, info-bulles, et clic
pour ouvrir la fiche de l'ouverture.

Route : GET /construction/openings/<int:dwg_file_id>
"""

import html as html_lib
import json
import math

from odoo import http
from odoo.http import request

PADDING_RATIO = 0.06
# Écart entre deux façades et entre une façade et son titre (m)
FACADE_GAP = 3.0
TITLE_SPACE = 1.2
# Hauteur d'étage supposée quand aucune façade validée ne la donne (m)
DEFAULT_FLOOR_HEIGHT = 2.80
# Hauteur dessinée pour une ouverture dont la hauteur est inconnue (m)
UNKNOWN_HEIGHT = 1.00
# Façades par ligne dans l'onglet Élévations
FACADES_PER_ROW = 2

ORIENTATION_ORDER = ("sud", "est", "nord", "ouest")
TYPE_COLORS = {
    "window": "#1976d2",
    "french_window": "#00897b",
    "bay": "#5e35b1",
    "door": "#8d6e63",
    "garage_door": "#6d4c41",
    "vent": "#757575",
    "unknown": "#9e9e9e",
}


def esc(value):
    return html_lib.escape(str(value if value is not None else ""), quote=True)


class ConstructionOpeningViewerController(http.Controller):

    @http.route("/construction/openings/<int:dwg_file_id>", type="http",
                auth="user", website=False)
    def opening_viewer(self, dwg_file_id, **kwargs):
        dwg = request.env["construction.dwg.files"].browse(dwg_file_id)
        if not dwg.exists():
            return request.not_found()

        openings = request.env["construction.opening"].search([
            "|", ("dwg_file_id", "=", dwg.id), ("source_file_ids", "in", dwg.id)])
        walls = request.env["construction.wall"].search([
            ("project_id", "=", dwg.project_id.id),
            ("level_id", "in", (openings.level_id | dwg.level_ids).ids),
        ]) if dwg.project_id else request.env["construction.wall"]

        data = [self._opening_to_dict(o) for o in openings]
        plan_svg = self._plan_svg(data, walls)
        elevation_svg = self._elevation_svg(data, dwg)
        return request.make_response(
            self._render_page(dwg, data, plan_svg, elevation_svg),
            headers=[("Content-Type", "text/html; charset=utf-8")])

    # --------------------------------------------------------
    # DONNÉES
    # --------------------------------------------------------

    @staticmethod
    def _opening_to_dict(o):
        type_labels = dict(o._fields["opening_type"].selection)
        return {
            "id": o.id,
            "name": o.name or "",
            "type": o.opening_type or "unknown",
            "type_label": type_labels.get(o.opening_type, ""),
            "position": o.wall_position or "unknown",
            "orientation": o.orientation or "",
            "level_id": o.level_id.id or 0,
            "level": o.level_id.name or "Sans niveau",
            "elevation": o.level_id.elevation or 0.0,
            "mark": o.mark or "",
            "offset": o.facade_offset,
            "has_axis": (o.start_x, o.start_y) != (o.end_x, o.end_y),
            "sx": o.start_x, "sy": o.start_y, "ex": o.end_x, "ey": o.end_y,
            "width": o.width, "thickness": o.thickness, "height": o.height,
            "sill": o.sill_height, "lintel": o.lintel_height,
            "complete": o.is_complete,
            "confidence": round(o.confidence or 0.0, 1),
            "wall": o.wall_id.name or "",
            "views": ", ".join(o.source_view_ids.mapped("name")),
        }

    @staticmethod
    def _tooltip(d):
        def m(value):
            return ("%.2f m" % value) if value else "?"
        lines = [
            "%s%s" % (d["name"], " [%s]" % d["mark"] if d["mark"] else ""),
            "%s · %s · %s" % (d["type_label"], d["level"],
                              d["orientation"] or ("intérieure" if d["position"] == "interior" else "-")),
            "Largeur %s · Épaisseur %s · Hauteur %s" % (m(d["width"]), m(d["thickness"]), m(d["height"])),
            "Allège %s · Sous linteau %s" % (m(d["sill"]) if d["height"] else "?", m(d["lintel"])),
            "Mur : %s" % (d["wall"] or "-"),
            "Vues : %s · Confiance %s %%" % (d["views"] or "-", d["confidence"]),
        ]
        if not d["complete"]:
            lines.append("⚠ Incomplète")
        return "\n".join(lines)

    def _group_attrs(self, d):
        return ('class="op" data-id="%d" data-type="%s" data-level="%d" '
                'data-complete="%d"' % (d["id"], esc(d["type"]), d["level_id"],
                                        1 if d["complete"] else 0))

    @staticmethod
    def _viewbox(xs, ys):
        if not xs:
            return "0 0 10 10"
        min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
        span = max(max_x - min_x, max_y - min_y, 1.0)
        pad = span * PADDING_RATIO
        return "%.3f %.3f %.3f %.3f" % (
            min_x - pad, min_y - pad, max_x - min_x + 2 * pad, max_y - min_y + 2 * pad)

    # --------------------------------------------------------
    # VUE EN PLAN (y du DXF vers le haut -> on inverse pour le SVG)
    # --------------------------------------------------------

    def _plan_svg(self, data, walls):
        xs, ys, parts = [], [], []

        for wall in walls:
            if (wall.start_x, wall.start_y) == (wall.end_x, wall.end_y):
                continue
            xs += [wall.start_x, wall.end_x]
            ys += [-wall.start_y, -wall.end_y]
            parts.append(
                '<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" class="wall" '
                'data-level="%d" stroke-width="%.3f"><title>%s</title></line>' % (
                    wall.start_x, -wall.start_y, wall.end_x, -wall.end_y,
                    wall.level_id.id or 0, max(wall.thickness or 0.0, 0.05),
                    esc("%s — ép. %.2f m" % (wall.name, wall.thickness or 0.0))))

        located = [d for d in data if d["has_axis"]]
        for d in located:
            xs += [d["sx"], d["ex"]]
            ys += [-d["sy"], -d["ey"]]
            color = TYPE_COLORS.get(d["type"], TYPE_COLORS["unknown"])
            depth = max(d["thickness"] or 0.0, 0.12)
            # Rectangle de l'ouverture : son axe dans le mur, sur l'épaisseur
            # du mur. Une cote manquante se lit au contour en pointillés.
            corners = self._axis_rectangle(d["sx"], -d["sy"], d["ex"], -d["ey"], depth)
            style = ('fill-opacity="0.85"' if d["complete"]
                     else 'fill-opacity="0.2" stroke-dasharray="0.10 0.06"')
            parts.append(
                '<g %s><polygon points="%s" fill="%s" stroke="%s" class="op-shape" %s/>'
                '<title>%s</title></g>' % (
                    self._group_attrs(d),
                    " ".join("%.3f,%.3f" % c for c in corners),
                    color, color, style, esc(self._tooltip(d))))
            if d["mark"]:
                parts.append(
                    '<text x="%.3f" y="%.3f" class="label" data-for="%d">%s</text>' % (
                        (d["sx"] + d["ex"]) / 2, -(d["sy"] + d["ey"]) / 2 - depth,
                        d["id"], esc(d["mark"])))

        unlocated = len(data) - len(located)
        return {
            "viewbox": self._viewbox(xs, ys),
            "content": "\n".join(parts),
            "count": len(located),
            "note": ("%d ouverture(s) vue(s) seulement en façade : voir l'onglet "
                     "Élévations." % unlocated) if unlocated else "",
        }

    @staticmethod
    def _axis_rectangle(x1, y1, x2, y2, depth):
        length = math.hypot(x2 - x1, y2 - y1) or 1.0
        nx, ny = -(y2 - y1) / length * depth / 2, (x2 - x1) / length * depth / 2
        return [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny),
                (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)]

    # --------------------------------------------------------
    # ÉLÉVATIONS : une façade par orientation, étages empilés
    # --------------------------------------------------------

    def _floor_heights(self, dwg):
        """Hauteur d'étage par niveau, prise sur les façades du projet
        (validées d'abord), sinon valeur par défaut."""
        heights = {}
        if not dwg.project_id:
            return heights
        bands = request.env["construction.facade.level"].search(
            [("facade_id.project_id", "=", dwg.project_id.id),
             ("level_id", "!=", False), ("height", ">", 0)],
            order="id")
        for band in bands.sorted(lambda b: not b.facade_id.is_validated):
            heights.setdefault(band.level_id.id, band.height)
        return heights

    def _facade_widths(self, dwg):
        widths = {}
        if dwg.project_id:
            for facade in request.env["construction.facade"].search(
                    [("project_id", "=", dwg.project_id.id), ("orientation", "!=", False)]):
                widths[facade.orientation] = max(widths.get(facade.orientation, 0.0),
                                                 facade.width)
        return widths

    def _elevation_svg(self, data, dwg):
        exterior = [d for d in data if d["orientation"] and d["offset"]]
        if not exterior:
            return {"viewbox": "0 0 10 10", "content": "", "count": 0,
                    "note": "Aucune ouverture rattachée à une façade."}

        floor_heights = self._floor_heights(dwg)
        widths = self._facade_widths(dwg)

        levels = sorted({(d["elevation"], d["level_id"], d["level"]) for d in exterior})
        # Bas de chaque étage : cumul des hauteurs d'étage connues
        base, level_base, level_height = 0.0, {}, {}
        for _elev, level_id, _name in levels:
            members = [d for d in exterior if d["level_id"] == level_id]
            needed = max([d["lintel"] or (d["sill"] + (d["height"] or UNKNOWN_HEIGHT))
                          for d in members] + [0.0]) + 0.3
            height = floor_heights.get(level_id) or max(DEFAULT_FLOOR_HEIGHT, needed)
            level_base[level_id], level_height[level_id] = base, height
            base += height
        total_height = base

        orientations = [o for o in ORIENTATION_ORDER
                        if any(d["orientation"] == o for d in exterior)]
        parts, x0, xs, ys = [], 0.0, [], []
        row_height = total_height + TITLE_SPACE + FACADE_GAP
        for index, orientation in enumerate(orientations):
            if index and not index % FACADES_PER_ROW:
                x0 = 0.0
            # Grille : chaque ligne de façades est décalée vers le bas
            dy = (index // FACADES_PER_ROW) * row_height
            members = [d for d in exterior if d["orientation"] == orientation]
            width = max([widths.get(orientation, 0.0)]
                        + [d["offset"] + (d["width"] or 0.0) / 2 + 0.5 for d in members])

            # Contour de la façade et lignes de plancher
            parts.append('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" class="facade"/>'
                         % (x0, dy - total_height, width, total_height))
            for _elev, level_id, name in levels:
                y = dy - level_base[level_id]
                parts.append('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" class="floor"/>'
                             % (x0, y, x0 + width, y))
                parts.append('<text x="%.3f" y="%.3f" class="level-label">%s</text>'
                             % (x0 + 0.1, y - 0.12, esc(name)))
            parts.append('<text x="%.3f" y="%.3f" class="facade-title">Façade %s</text>'
                         % (x0 + width / 2, dy + TITLE_SPACE * 0.8, esc(orientation.upper())))

            for d in members:
                w = d["width"] or 0.6
                h = d["height"] or UNKNOWN_HEIGHT
                bottom = level_base.get(d["level_id"], 0.0) + (d["sill"] if d["height"] else 0.9)
                x, y = x0 + d["offset"] - w / 2, dy - (bottom + h)
                color = TYPE_COLORS.get(d["type"], TYPE_COLORS["unknown"])
                dash = '' if d["complete"] else ' stroke-dasharray="0.12 0.08"'
                fill_opacity = "0.35" if d["complete"] else "0.12"
                label = d["mark"] or ("h ?" if not d["height"] else "")
                parts.append(
                    '<g %s><rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" '
                    'fill="%s" fill-opacity="%s" stroke="%s" class="op-shape"%s/>'
                    '<title>%s</title></g>' % (
                        self._group_attrs(d), x, y, w, h, color, fill_opacity, color,
                        dash, esc(self._tooltip(d))))
                if label:
                    parts.append('<text x="%.3f" y="%.3f" class="label" data-for="%d">%s</text>'
                                 % (x + w / 2, y + h / 2 + 0.1, d["id"], esc(label)))

            xs += [x0, x0 + width]
            ys += [dy - total_height, dy + TITLE_SPACE]
            x0 += width + FACADE_GAP

        return {"viewbox": self._viewbox(xs, ys), "content": "\n".join(parts),
                "count": len(exterior), "note": ""}

    # --------------------------------------------------------
    # PAGE
    # --------------------------------------------------------

    def _render_page(self, dwg, data, plan, elevation):
        title = esc(dwg.filename or "Fichier #%d" % dwg.id)
        levels = sorted({(d["elevation"], d["level_id"], d["level"]) for d in data})
        level_options = "".join('<option value="%d">%s</option>' % (lid, esc(name))
                                for _e, lid, name in levels)
        types = sorted({(d["type"], d["type_label"]) for d in data})
        type_options = "".join('<option value="%s">%s</option>' % (esc(t), esc(label))
                               for t, label in types)
        legend = "".join(
            '<div><span class="swatch" style="background:%s"></span>%s</div>' % (color, esc(label))
            for t, label in types for color in [TYPE_COLORS.get(t, TYPE_COLORS["unknown"])])
        stats = {
            "total": len(data),
            "complete": sum(1 for d in data if d["complete"]),
            "doors": sum(1 for d in data if d["type"] in ("door", "garage_door")),
            "windows": sum(1 for d in data if d["type"] in ("window", "french_window", "bay")),
        }
        # Vue d'ouverture : élévations si rien n'est localisé en plan
        start_tab = "plan" if plan["count"] or not elevation["count"] else "elevation"
        form_url = "/web#model=construction.opening&view_type=form&id="

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Ouvertures — {title}</title>
<style>
  :root {{ --bg:#f4f4f4; --panel:#fff; --ink:#333; --muted:#777; --line:#ddd;
          --wall:#b0b0b0; --facade:#fafafa; }}
  html, body {{ margin:0; height:100%; font-family:-apple-system,"Segoe UI",sans-serif;
               background:var(--bg); color:var(--ink); }}
  #toolbar {{ position:fixed; inset:0 0 auto 0; z-index:10; background:var(--panel);
             border-bottom:1px solid var(--line); padding:8px 16px; display:flex;
             align-items:center; gap:12px; flex-wrap:wrap; box-shadow:0 1px 4px rgba(0,0,0,.08); }}
  #toolbar h1 {{ font-size:15px; margin:0; font-weight:600; }}
  #toolbar label {{ font-size:12px; color:#555; display:flex; align-items:center; gap:4px; }}
  select, button {{ font-size:12px; padding:4px 8px; }}
  .stat {{ font-size:12px; padding:3px 9px; border-radius:10px; background:#eee; }}
  .stat.green {{ background:#e8f5e9; color:#2e7d32; }}
  .tabs {{ display:flex; gap:4px; }}
  .tabs button {{ border:1px solid var(--line); background:#fff; border-radius:4px; cursor:pointer; }}
  .tabs button.active {{ background:#1976d2; color:#fff; border-color:#1976d2; }}
  .view {{ position:absolute; top:var(--top,56px); left:0; right:0; bottom:0; background:#fff;
          overflow:hidden; cursor:grab; display:none; }}
  .view.active {{ display:block; }}
  .view.dragging {{ cursor:grabbing; }}
  .view svg {{ width:100%; height:100%; display:block; }}
  .note {{ position:absolute; top:10px; left:50%; transform:translateX(-50%); font-size:12px;
          background:#fff8e1; color:#8d6e00; padding:4px 10px; border-radius:4px; }}
  .wall {{ stroke:var(--wall); stroke-linecap:square; }}
  .facade {{ fill:var(--facade); stroke:#444; stroke-width:0.04; }}
  .floor {{ stroke:#999; stroke-width:0.03; stroke-dasharray:0.2 0.1; }}
  .level-label {{ font-size:0.28px; fill:var(--muted); }}
  .facade-title {{ font-size:0.45px; font-weight:600; text-anchor:middle; fill:var(--ink); }}
  .label {{ font-size:0.26px; text-anchor:middle; fill:#222; pointer-events:none; }}
  .op {{ cursor:pointer; }}
  /* Contours en mètres (le viewBox est en mètres) */
  #view-elevation .op-shape {{ stroke-width:0.04; }}
  #view-plan .op-shape {{ stroke-width:0.03; }}
  .op:hover .op-shape {{ stroke:#e53935 !important; }}
  .hidden {{ display:none; }}
  #legend {{ position:fixed; bottom:16px; left:16px; background:var(--panel); border:1px solid var(--line);
            border-radius:6px; padding:8px 12px; font-size:12px; box-shadow:0 1px 4px rgba(0,0,0,.1); }}
  #legend div {{ display:flex; align-items:center; gap:6px; margin:2px 0; }}
  #legend .swatch {{ width:14px; height:8px; border-radius:2px; }}
  #legend .dashed {{ width:14px; height:8px; border:1px dashed #777; }}
</style>
</head>
<body>
<div id="toolbar">
  <h1>🚪 Ouvertures — {title}</h1>
  <div class="tabs">
    <button data-tab="plan">Vue en plan ({plan['count']})</button>
    <button data-tab="elevation">Élévations ({elevation['count']})</button>
  </div>
  <span class="stat">{stats['total']} ouvertures</span>
  <span class="stat">{stats['windows']} fenêtres · {stats['doors']} portes</span>
  <span class="stat green">{stats['complete']} complètes</span>
  <label>Niveau : <select id="f-level"><option value="">Tous</option>{level_options}</select></label>
  <label>Nature : <select id="f-type"><option value="">Toutes</option>{type_options}</select></label>
  <label><input type="checkbox" id="f-incomplete"/> Incomplètes seulement</label>
  <button id="reset" style="margin-left:auto">Réinitialiser la vue</button>
</div>

<div class="view" id="view-plan">
  {'<div class="note">%s</div>' % esc(plan['note']) if plan['note'] else ''}
  <svg viewBox="{plan['viewbox']}" data-viewbox="{plan['viewbox']}" preserveAspectRatio="xMidYMid meet">
    {plan['content']}
  </svg>
</div>
<div class="view" id="view-elevation">
  {'<div class="note">%s</div>' % esc(elevation['note']) if elevation['note'] else ''}
  <svg viewBox="{elevation['viewbox']}" data-viewbox="{elevation['viewbox']}" preserveAspectRatio="xMidYMid meet">
    {elevation['content']}
  </svg>
</div>

<div id="legend">
  {legend}
  <div><span class="dashed"></span>Incomplète : largeur, épaisseur ou hauteur manquante</div>
</div>

<script>
(function () {{
  const FORM_URL = {json.dumps(form_url)};
  const toolbar = document.getElementById('toolbar');
  const setTop = () => document.documentElement.style.setProperty('--top', toolbar.offsetHeight + 'px');
  setTop(); window.addEventListener('resize', setTop);

  // Onglets
  const tabs = document.querySelectorAll('.tabs button');
  function show(tab) {{
    tabs.forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + tab));
  }}
  tabs.forEach(b => b.addEventListener('click', () => show(b.dataset.tab)));
  show({json.dumps(start_tab)});

  // Zoom / déplacement : on agit sur le viewBox de chaque SVG (unités = mètres)
  document.querySelectorAll('.view').forEach(view => {{
    const svg = view.querySelector('svg');
    let vb = svg.dataset.viewbox.split(' ').map(Number);
    let drag = null, moved = false;
    const apply = () => svg.setAttribute('viewBox', vb.join(' '));
    const toWorld = (e) => {{
      const r = svg.getBoundingClientRect();
      const s = Math.max(vb[2] / r.width, vb[3] / r.height);
      const ox = vb[0] + (vb[2] - r.width * s) / 2, oy = vb[1] + (vb[3] - r.height * s) / 2;
      return [ox + (e.clientX - r.left) * s, oy + (e.clientY - r.top) * s, s];
    }};
    view.addEventListener('wheel', (e) => {{
      e.preventDefault();
      const [wx, wy] = toWorld(e);
      const k = e.deltaY < 0 ? 1 / 1.15 : 1.15;
      vb = [wx - (wx - vb[0]) * k, wy - (wy - vb[1]) * k, vb[2] * k, vb[3] * k];
      apply();
    }}, {{ passive: false }});
    view.addEventListener('mousedown', (e) => {{ drag = [e.clientX, e.clientY]; moved = false; view.classList.add('dragging'); }});
    window.addEventListener('mousemove', (e) => {{
      if (!drag || !view.classList.contains('active')) return;
      const s = toWorld(e)[2];
      if (Math.abs(e.clientX - drag[0]) + Math.abs(e.clientY - drag[1]) > 2) moved = true;
      vb[0] -= (e.clientX - drag[0]) * s; vb[1] -= (e.clientY - drag[1]) * s;
      drag = [e.clientX, e.clientY]; apply();
    }});
    window.addEventListener('mouseup', () => {{ drag = null; view.classList.remove('dragging'); }});
    view.addEventListener('click', (e) => {{
      const op = e.target.closest('.op');
      if (op && !moved) window.open(FORM_URL + op.dataset.id, '_blank');
    }});
    view._reset = () => {{ vb = svg.dataset.viewbox.split(' ').map(Number); apply(); }};
  }});
  document.getElementById('reset').addEventListener('click',
    () => document.querySelectorAll('.view').forEach(v => v._reset()));

  // Filtres
  const fLevel = document.getElementById('f-level');
  const fType = document.getElementById('f-type');
  const fIncomplete = document.getElementById('f-incomplete');
  function filter() {{
    document.querySelectorAll('.op').forEach(g => {{
      const hide = (fLevel.value && g.dataset.level !== fLevel.value)
        || (fType.value && g.dataset.type !== fType.value)
        || (fIncomplete.checked && g.dataset.complete === '1');
      g.classList.toggle('hidden', !!hide);
      document.querySelectorAll('.label[data-for="' + g.dataset.id + '"]')
        .forEach(t => t.classList.toggle('hidden', !!hide));
    }});
    document.querySelectorAll('.wall').forEach(w =>
      w.classList.toggle('hidden', !!(fLevel.value && w.dataset.level !== fLevel.value)));
  }}
  [fLevel, fType, fIncomplete].forEach(el => el.addEventListener('change', filter));
}})();
</script>
</body>
</html>"""
