"""Schéma coté d'un élément de construction (SVG), dessiné depuis ses dimensions.

Le schéma ne reproduit pas le plan DXF : il donne, pour chaque type
d'ouvrage, les vues qui servent à le lire (plan, coupe, élévation), à
l'échelle de ses propres cotes. Une cote absente est dessinée à une valeur
de convention, en pointillés, et affichée « ? m » : le schéma reste lisible
et montre aussitôt ce qu'il manque.
"""
from html import escape

TYPE_COLORS = {
    "semelle": "#1565c0",
    "poteau": "#6a1b9a",
    "semelle_filante": "#2e7d32",
    "longrine": "#e65100",
    "mur": "#455a64",
}
DEFAULT_COLOR = "#37474f"

# Valeur dessinée à la place d'une cote manquante (m).
PLACEHOLDER = {"l": 1.0, "w": 0.4, "h": 0.5}

VIEW_W, VIEW_H = 260, 190      # cadre d'une vue (px)
MARGIN = 46                    # place des cotes autour de la forme
MIN_SIDE = 6                   # un côté très fin reste visible


def _fmt(value):
    return ("%.2f m" % value) if value else "? m"


def _views(type_code):
    """Vues à dessiner : (titre, cote horizontale, cote verticale, options)."""
    if type_code == "poteau":
        return [("Section", "l", "w", {"rebars": True}),
                ("Élévation", "w", "h", {"ground": "base"})]
    if type_code in ("semelle_filante", "longrine"):
        return [("Vue en plan", "l", "w", {}),
                ("Coupe transversale", "w", "h",
                 {"rebars": True,
                  "ground": "above" if type_code == "semelle_filante" else None})]
    if type_code == "mur":
        return [("Élévation", "l", "h", {"ground": "base"}),
                ("Vue en plan", "l", "w", {})]
    if type_code == "semelle":
        return [("Vue en plan", "l", "w", {"column": True}),
                ("Coupe", "l", "h", {"ground": "above", "column": True})]
    return [("Vue en plan", "l", "w", {}), ("Élévation", "l", "h", {})]


def _view_svg(x0, title, hkey, vkey, opts, dims, color):
    real_h, real_v = dims.get(hkey) or 0.0, dims.get(vkey) or 0.0
    draw_h = real_h or PLACEHOLDER[hkey]
    draw_v = real_v or PLACEHOLDER[vkey]
    missing = not (real_h and real_v)

    avail_w, avail_h = VIEW_W - 2 * MARGIN, VIEW_H - 2 * MARGIN
    scale = min(avail_w / draw_h, avail_h / draw_v)
    w = max(draw_h * scale, MIN_SIDE)
    h = max(draw_v * scale, MIN_SIDE)
    x = x0 + (VIEW_W - w) / 2
    y = MARGIN / 2 + 14 + (avail_h - h) / 2 + MARGIN / 2

    out = [
        '<text x="%.1f" y="16" text-anchor="middle" class="t">%s</text>'
        % (x0 + VIEW_W / 2, escape(title)),
    ]

    # Terrain : au pied d'un ouvrage en élévation, au-dessus d'une fondation enterrée.
    if opts.get("ground"):
        gy = y + h if opts["ground"] == "base" else max(y - 30, 22)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="g"/>'
                   % (x - 18, gy, x + w + 18, gy))

    out.append(
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" '
        'fill-opacity="0.18" stroke="%s" stroke-width="1.6"%s/>'
        % (x, y, w, h, color, color,
           ' stroke-dasharray="5 3"' if missing else ""))

    if opts.get("column"):
        # Amorce du poteau porté par la semelle.
        cw = max(min(w, h) * 0.28, MIN_SIDE)
        if vkey == "h":
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                       'class="c"/>' % (x + (w - cw) / 2, y - 22, cw, 22))
        else:
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                       'class="c"/>' % (x + (w - cw) / 2, y + (h - cw) / 2, cw, cw))

    if opts.get("rebars") and w > 14 and h > 14:
        inset = min(w, h) * 0.18
        for cx in (x + inset, x + w - inset):
            for cy in (y + inset, y + h - inset):
                out.append('<circle cx="%.1f" cy="%.1f" r="2.6" class="r"/>'
                           % (cx, cy))

    # Cote horizontale (sous la forme).
    dy = y + h + 16
    out.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="d" '
        'marker-start="url(#a)" marker-end="url(#a)"/>' % (x, dy, x + w, dy))
    out.append('<text x="%.1f" y="%.1f" text-anchor="middle" class="v">%s</text>'
               % (x + w / 2, dy + 13, _fmt(real_h)))

    # Cote verticale (à gauche de la forme).
    dx = x - 16
    out.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="d" '
        'marker-start="url(#a)" marker-end="url(#a)"/>' % (dx, y, dx, y + h))
    out.append('<text x="%.1f" y="%.1f" text-anchor="middle" class="v" '
               'transform="rotate(-90 %.1f %.1f)">%s</text>'
               % (dx - 6, y + h / 2, dx - 6, y + h / 2, _fmt(real_v)))
    return "".join(out), missing


def render_element_sketch(type_code, dims, label=""):
    """SVG du schéma coté d'un élément.

    :param type_code: code du type d'élément (semelle, poteau, mur…)
    :param dims: {'l': longueur, 'w': largeur/épaisseur, 'h': hauteur} en m
    :param label: repère affiché en légende (ex. « S1 »)
    """
    color = TYPE_COLORS.get(type_code, DEFAULT_COLOR)
    views = _views(type_code)
    total_w = VIEW_W * len(views)

    parts, any_missing = [], False
    for i, (title, hkey, vkey, opts) in enumerate(views):
        svg, missing = _view_svg(i * VIEW_W, title, hkey, vkey, opts, dims, color)
        parts.append(svg)
        any_missing = any_missing or missing

    legend = escape(label or "")
    if any_missing:
        legend += (" — " if legend else "") + "cotes manquantes en pointillés"

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
        'style="width:100%%;max-width:%dpx;height:auto;font-family:sans-serif">'
        '<defs><marker id="a" viewBox="0 0 10 10" refX="5" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M0,2 L5,5 L0,8" fill="none" stroke="#555"/></marker>'
        '<style>'
        '.t{font-size:12px;font-weight:600;fill:#333}'
        '.v{font-size:11px;fill:#222}'
        '.d{stroke:#555;stroke-width:.8}'
        '.g{stroke:#8d6e63;stroke-width:1.2;stroke-dasharray:6 3}'
        '.c{fill:#9e9e9e;fill-opacity:.35;stroke:#616161;stroke-width:1}'
        '.r{fill:#212121}'
        '.l{font-size:11px;fill:#777}'
        '</style></defs>'
        '%s'
        '<text x="%d" y="%d" text-anchor="middle" class="l">%s</text>'
        '</svg>'
        % (total_w, VIEW_H + 20, total_w, "".join(parts),
           total_w // 2, VIEW_H + 14, legend)
    )
