# -*- coding: utf-8 -*-
"""
VILLA R+1 - 4 chambres - ~185 m2 habitables
Emprise 12.00 x 9.00 m - 2 niveaux
Genere un DXF contenant : plan RDC, plan Etage, 4 facades
Enregistrer ensuite en .DWG depuis AutoCAD : Fichier > Enregistrer sous > *.dwg
"""

import math
import ezdxf
from ezdxf.enums import TextEntityAlignment

# ------------------------------------------------------------------ document
doc = ezdxf.new("R2010", setup=True)
doc.units = 6
msp = doc.modelspace()

for nom, coul in [("MURS_EXT", 7), ("MURS_INT", 8), ("OUVERTURES", 4),
                  ("ESCALIER", 3), ("TEXTE", 2), ("COTES", 1), ("TERRAIN", 3)]:
    doc.layers.add(nom, color=coul)

# ------------------------------------------------------------------ outils plan
def rect(x1, y1, x2, y2, couche="MURS_INT"):
    msp.add_lwpolyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
                       close=True, dxfattribs={"layer": couche})

def _decoupe(bornes, trous):
    for (a, b) in sorted(trous):
        out = []
        for (c, d) in bornes:
            if b <= c or a >= d:
                out.append((c, d))
            else:
                if c < a: out.append((c, a))
                if b < d: out.append((b, d))
        bornes = out
    return bornes

def mur_h(x1, x2, y, ep=0.10, trous=(), couche="MURS_INT"):
    for (a, b) in _decoupe([(x1, x2)], trous):
        if b - a > 1e-6:
            rect(a, y - ep / 2, b, y + ep / 2, couche)

def mur_v(y1, y2, x, ep=0.10, trous=(), couche="MURS_INT"):
    for (a, b) in _decoupe([(y1, y2)], trous):
        if b - a > 1e-6:
            rect(x - ep / 2, a, x + ep / 2, b, couche)

def texte(x, y, lignes, h=0.20, couche="TEXTE"):
    if isinstance(lignes, str): lignes = [lignes]
    for i, s in enumerate(lignes):
        t = msp.add_text(s, height=h, dxfattribs={"layer": couche})
        t.set_placement((x, y - i * h * 1.4), align=TextEntityAlignment.MIDDLE_CENTER)

def porte(x, y, larg=0.90, angle=0.0, sens=1):
    a0 = math.radians(angle)
    a1 = a0 + sens * math.radians(90)
    msp.add_arc(center=(x, y), radius=larg,
                start_angle=math.degrees(a0), end_angle=math.degrees(a1),
                dxfattribs={"layer": "OUVERTURES"})
    msp.add_line((x, y), (x + larg * math.cos(a1), y + larg * math.sin(a1)),
                 dxfattribs={"layer": "OUVERTURES"})

def fenetre(x1, y1, x2, y2):
    rect(x1, y1, x2, y2, "OUVERTURES")
    if abs(x2 - x1) > abs(y2 - y1):
        y = (y1 + y2) / 2
        msp.add_line((x1, y), (x2, y), dxfattribs={"layer": "OUVERTURES"})
    else:
        x = (x1 + x2) / 2
        msp.add_line((x, y1), (x, y2), dxfattribs={"layer": "OUVERTURES"})

def escalier(x, y):
    L = 2.40
    msp.add_line((x + 1.05, y), (x + 1.05, y + 1.80), dxfattribs={"layer": "ESCALIER"})
    msp.add_line((x + 1.35, y), (x + 1.35, y + 1.80), dxfattribs={"layer": "ESCALIER"})
    for k in range(1, 7):
        yy = y + k * 0.26
        msp.add_line((x, yy), (x + 1.05, yy), dxfattribs={"layer": "ESCALIER"})
        msp.add_line((x + 1.35, yy), (x + L, yy), dxfattribs={"layer": "ESCALIER"})
    msp.add_line((x, y + 1.80), (x + L, y + 1.80), dxfattribs={"layer": "ESCALIER"})
    msp.add_line((x + 0.50, y + 0.10), (x + 0.50, y + 1.60), dxfattribs={"layer": "ESCALIER"})
    msp.add_line((x + 0.50, y + 1.60), (x + 0.35, y + 1.35), dxfattribs={"layer": "ESCALIER"})
    msp.add_line((x + 0.50, y + 1.60), (x + 0.65, y + 1.35), dxfattribs={"layer": "ESCALIER"})

def cote_h(x1, x2, y, ybase):
    dim = msp.add_linear_dim(base=(0, ybase), p1=(x1, y), p2=(x2, y),
                             dxfattribs={"layer": "COTES"})
    dim.render()

def cote_v(y1, y2, x, xbase):
    dim = msp.add_linear_dim(base=(xbase, 0), p1=(x, y1), p2=(x, y2),
                             dxfattribs={"layer": "COTES"}, angle=90)
    dim.render()

# ==================================================================
#  NIVEAU  (plan RDC ou Etage)
# ==================================================================
def niveau(oy, titre, rdc=True):
    def MH(x1, x2, y, ep=0.10, trous=(), c="MURS_INT"):
        mur_h(x1, x2, y + oy, ep, trous, c)
    def MV(y1, y2, x, ep=0.10, trous=(), c="MURS_INT"):
        mur_v(y1 + oy, y2 + oy, x, ep, trous, c)
    def TX(x, y, lignes, h=0.20):
        texte(x, y + oy, lignes, h)
    def PO(x, y, larg=0.90, angle=0.0, sens=1):
        porte(x, y + oy, larg, angle, sens)
    def FE(x1, y1, x2, y2):
        fenetre(x1, y1 + oy, x2, y2 + oy)
    def ESC(x, y):
        escalier(x, y + oy)

    if rdc:
        MH(0, 12.00, 0.15, 0.30, [(0.80, 2.60), (3.20, 4.60), (5.60, 6.60)])
        MH(0, 12.00, 8.85, 0.30, [(1.20, 3.40), (7.90, 10.00)])
        MV(0.30, 8.70, 0.15, 0.30, [(1.20, 3.40), (6.40, 8.00)])
        MV(0.30, 8.70, 11.85, 0.30, [(1.20, 3.40), (6.40, 8.00)])
    else:
        MH(0, 12.00, 0.15, 0.30, [(1.20, 2.80), (3.40, 4.60)])
        MH(0, 12.00, 8.85, 0.30, [(1.20, 3.40), (5.60, 7.00), (8.20, 10.00)])
        MV(0.30, 8.70, 0.15, 0.30, [(1.00, 3.00), (6.20, 8.00)])
        MV(0.30, 8.70, 11.85, 0.30, [(1.00, 3.00), (6.20, 8.00)])

    if rdc:
        MV(0.30, 8.70, 4.95, 0.10, [(1.00, 1.90), (6.30, 7.10)])
        MV(0.30, 8.70, 7.45, 0.10, [(1.00, 1.90), (6.30, 7.10)])
        MH(0.30, 11.70, 5.75, 0.10, [(5.90, 6.90)])
        MH(5.00, 6.50, 7.25, 0.10)
        MV(5.75, 7.25, 6.45, 0.10, [(6.10, 6.90)])
        ESC(5.00, 3.30)
    else:
        MV(0.30, 8.70, 4.95, 0.10, [(3.20, 4.60), (4.95, 5.65)])
        MV(0.30, 8.70, 7.45, 0.10, [(1.20, 2.00), (3.80, 4.60), (6.10, 6.90)])
        MH(0.30, 4.90, 4.85, 0.10)
        MV(0.30, 4.80, 2.65, 0.10, [(3.60, 4.40)])
        MH(2.70, 4.90, 2.65, 0.10, [(3.00, 3.80)])
        MH(5.00, 7.40, 5.75, 0.10, [(5.80, 6.80)])
        MH(7.50, 11.70, 3.25, 0.10)
        ESC(5.00, 3.30)

    if rdc:
        PO(5.60, 0.30, 1.00, 0); PO(4.90, 1.00, 0.90, 0, 1)
        PO(7.50, 1.00, 0.90, 180, 1); PO(6.45, 6.10, 0.80, 0, -1)
        PO(4.95, 6.30, 0.80, 0, -1); PO(7.45, 6.30, 0.80, 0, 1)
    else:
        PO(4.95, 3.20, 1.40, 0, -1); PO(4.95, 4.95, 0.90, 0, 1)
        PO(2.65, 3.60, 0.80, 0, -1); PO(3.00, 2.65, 0.80, 0, 1)
        PO(7.45, 1.20, 0.80, 0, 1); PO(7.45, 3.80, 0.80, 0, 1)
        PO(7.45, 6.10, 0.80, 0, 1)

    if rdc:
        FE(0.80, 0.00, 2.60, 0.30); FE(3.20, 0.00, 4.60, 0.30)
        FE(0.00, 1.20, 0.30, 3.40); FE(0.00, 6.40, 0.30, 8.00)
        FE(1.20, 8.70, 3.40, 9.00); FE(7.90, 8.70, 10.00, 9.00)
        FE(11.70, 1.20, 12.00, 3.40); FE(11.70, 6.40, 12.00, 8.00)
    else:
        FE(1.20, 0.00, 2.80, 0.30); FE(3.40, 0.00, 4.60, 0.30)
        FE(0.00, 1.00, 0.30, 3.00); FE(0.00, 6.20, 0.30, 8.00)
        FE(1.20, 8.70, 3.40, 9.00); FE(5.60, 8.70, 7.00, 9.00)
        FE(8.20, 8.70, 10.00, 9.00); FE(11.70, 1.00, 12.00, 3.00)
        FE(11.70, 6.20, 12.00, 8.00)

    TX(6.00, 10.20, [titre], 0.45)
    if rdc:
        TX(2.60, 3.00, ["SEJOUR", "24.8 m2"])
        TX(9.60, 3.00, ["CUISINE +", "SALLE A MANGER", "22.7 m2"])
        TX(9.60, 7.20, ["BUREAU /", "CHAMBRE D'AMIS", "12.2 m2"])
        TX(2.60, 7.20, ["BUANDERIE /", "CELLIER", "13.3 m2"])
        TX(6.20, 1.70, ["HALL", "7.0 m2"])
        TX(6.20, 4.50, ["ESCALIER", "5.8 m2"])
        TX(5.70, 6.50, ["WC", "2.0 m2"])
        TX(6.80, 8.10, ["DEGAG.", "5.0 m2"])
        TX(6.00, -1.30, ["REZ-DE-CHAUSSEE  -  92.8 m2"], 0.35)
    else:
        TX(2.60, 6.80, ["CHAMBRE 1", "(parentale)", "17.5 m2"])
        TX(1.45, 2.50, ["CHAMBRE 2", "10.4 m2"])
        TX(3.80, 1.45, ["SDB 1", "5.1 m2"])
        TX(3.80, 3.70, ["DEGAG.", "4.6 m2"])
        TX(9.60, 7.20, ["CHAMBRE 3", "12.2 m2"])
        TX(9.60, 4.50, ["CHAMBRE 4", "10.1 m2"])
        TX(9.60, 1.70, ["SALLE D'EAU", "/ BUANDERIE", "12.2 m2"])
        TX(6.20, 1.70, ["COULOIR", "7.0 m2"])
        TX(6.20, 4.50, ["PALIER", "5.8 m2"])
        TX(6.20, 7.20, ["DEGAG.", "7.0 m2"])
        TX(6.00, -1.30, ["ETAGE  -  91.9 m2"], 0.35)

    cote_h(0, 12.00, 0 + oy, -2.20 + oy)
    cote_v(0, 9.00, 0, -2.20)

# ==================================================================
#  FACADE
#  ox,oy : coin inferieur gauche (niveau 0.00 du sol)
#  longueur : 12 (S/N) ou 9 (E/O)
#  sens : 1 = x plan croissant a droite ; -1 = inverse (vue de l'exterieur)
#  Ouvertures : (x1, x2, 'fenetre'|'porte')
# ==================================================================
def facade(ox, oy, titre, longueur, rdc_ouvs, etage_ouvs, sens=1):
    H_RDC_PLAF = 2.80      # plafond RDC
    H_ETAGE_NIV = 3.00     # niveau plancher etage
    H_ETAGE_PLAF = 5.80    # plafond etage / toiture
    H_ACROTERE = 6.20      # dessus acrotere
    SILL_RDC, HEAD_RDC = 0.90, 2.30
    SILL_ET, HEAD_ET = 3.90, 5.30
    PORTE_H = 2.20

    # --- terrain (ligne + hachures) ---
    msp.add_line((ox - 0.60, oy), (ox + longueur + 0.60, oy),
                 dxfattribs={"layer": "TERRAIN"})
    n = int(longueur) + 3
    for i in range(n):
        x = ox - 0.60 + i * (longueur + 1.20) / n
        msp.add_line((x, oy), (x - 0.25, oy - 0.15),
                     dxfattribs={"layer": "TERRAIN"})

    # --- murs (rectangle principal 0 -> 5.80) ---
    msp.add_lwpolyline([(ox, oy), (ox + longueur, oy),
                        (ox + longueur, oy + H_ETAGE_PLAF),
                        (ox, oy + H_ETAGE_PLAF)],
                       close=True, dxfattribs={"layer": "MURS_EXT"})

    # --- acrotere / parapet ---
    msp.add_lwpolyline([(ox - 0.10, oy + H_ETAGE_PLAF),
                        (ox + longueur + 0.10, oy + H_ETAGE_PLAF),
                        (ox + longueur + 0.10, oy + H_ACROTERE),
                        (ox - 0.10, oy + H_ACROTERE)],
                       close=True, dxfattribs={"layer": "MURS_EXT"})

    # --- ligne plancher etage + bandeau ---
    msp.add_line((ox, oy + H_ETAGE_NIV), (ox + longueur, oy + H_ETAGE_NIV),
                 dxfattribs={"layer": "MURS_INT"})

    # --- reperes de niveau ---
    texte(ox - 1.10, oy, "+0.00", 0.15, "COTES")
    texte(ox - 1.10, oy + H_ETAGE_NIV, "+3.00", 0.15, "COTES")
    texte(ox - 1.10, oy + H_ETAGE_PLAF, "+5.80", 0.15, "COTES")
    texte(ox - 1.10, oy + H_ACROTERE, "+6.20", 0.15, "COTES")

    # --- ouvertures RDC ---
    for (x1, x2, typ) in rdc_ouvs:
        if sens == -1:
            x1, x2 = longueur - x2, longueur - x1
        yb, yh = (0.00, PORTE_H) if typ == "porte" else (SILL_RDC, HEAD_RDC)
        msp.add_lwpolyline([(ox + x1, oy + yb), (ox + x2, oy + yb),
                            (ox + x2, oy + yh), (ox + x1, oy + yh)],
                           close=True, dxfattribs={"layer": "OUVERTURES"})
        xm = ox + (x1 + x2) / 2
        if typ == "fenetre":
            msp.add_line((xm, oy + yb), (xm, oy + yh),
                         dxfattribs={"layer": "OUVERTURES"})
        else:
            msp.add_line((ox + x1 + 0.10, oy + yh - 0.05),
                         (ox + x2 - 0.10, oy + yh - 0.05),
                         dxfattribs={"layer": "OUVERTURES"})

    # --- ouvertures etage ---
    for (x1, x2, typ) in etage_ouvs:
        if sens == -1:
            x1, x2 = longueur - x2, longueur - x1
        yb, yh = SILL_ET, HEAD_ET
        msp.add_lwpolyline([(ox + x1, oy + yb), (ox + x2, oy + yb),
                            (ox + x2, oy + yh), (ox + x1, oy + yh)],
                           close=True, dxfattribs={"layer": "OUVERTURES"})
        xm = ox + (x1 + x2) / 2
        msp.add_line((xm, oy + yb), (xm, oy + yh),
                     dxfattribs={"layer": "OUVERTURES"})

    # --- titre ---
    texte(ox + longueur / 2, oy - 1.40, titre, 0.40, "TEXTE")

# ==================================================================
#  DESSIN
# ==================================================================
niveau(0.0, "PLAN RDC", rdc=True)
niveau(13.50, "PLAN ETAGE", rdc=False)

OY_FAC = -18.0

# Facade SUD : porte d'entree + 2 fenetres RDC ; 2 fenetres etage
facade(0, OY_FAC, "FACADE SUD", 12,
       rdc_ouvs=[(0.80, 2.60, "fenetre"),
                 (3.20, 4.60, "fenetre"),
                 (5.60, 6.60, "porte")],
       etage_ouvs=[(1.20, 2.80, "fenetre"),
                   (3.40, 4.60, "fenetre")],
       sens=1)

# Facade NORD (vue de l'exterieur : x inverse)
facade(14, OY_FAC, "FACADE NORD", 12,
       rdc_ouvs=[(1.20, 3.40, "fenetre"),
                 (7.90, 10.00, "fenetre")],
       etage_ouvs=[(1.20, 3.40, "fenetre"),
                   (5.60, 7.00, "fenetre"),
                   (8.20, 10.00, "fenetre")],
       sens=-1)

# Facade EST (on lit le plan en y, longueur 9 m)
facade(28, OY_FAC, "FACADE EST", 9,
       rdc_ouvs=[(1.20, 3.40, "fenetre"),
                 (6.40, 8.00, "fenetre")],
       etage_ouvs=[(1.00, 3.00, "fenetre"),
                   (6.20, 8.00, "fenetre")],
       sens=1)

# Facade OUEST (vue exterieure : y inverse)
facade(39, OY_FAC, "FACADE OUEST", 9,
       rdc_ouvs=[(1.20, 3.40, "fenetre"),
                 (6.40, 8.00, "fenetre")],
       etage_ouvs=[(1.00, 3.00, "fenetre"),
                   (6.20, 8.00, "fenetre")],
       sens=-1)

# ---------------- cartouche ----------------
texte(6.00, -22.00, ["VILLA R+1  -  4 CHAMBRES  -  ~185 m2 HABITABLES",
                     "Emprise 12.00 x 9.00 m  -  HSP 2.50 m  -  Toiture-terrasse",
                     "Esquisse - a faire valider par un architecte"], 0.30, "TEXTE")

doc.saveas("villa_r1_4chambres.dxf")
print("Fichier villa_r1_4chambres.dxf genere avec plans + 4 facades.")