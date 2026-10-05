# -*- coding: utf-8 -*-
"""
VILLA R+1 - PLANS D'EXECUTION (BET indicatif)
==============================================
Genere 6 fichiers DXF a convertir en DWG :
  PE-01-FONDATIONS.dxf
  PE-02-COFFRAGE-RDC.dxf
  PE-03-COFFRAGE-ETAGE.dxf
  PE-04-ELECTRICITE.dxf
  PE-05-PLOMBERIE.dxf
  PE-06-COUPES-DETAILS.dxf
"""

import math
import ezdxf
from ezdxf.enums import TextEntityAlignment

# ============================================================ CONSTANTES
LX, LY = 12.00, 9.00
EP_EXT, EP_INT = 0.30, 0.10
HSP = 2.50
H_RDC_SOL = 0.00
H_RDC_PLAF = 2.80
H_ETAGE_SOL = 3.00
H_ETAGE_PLAF = 5.80
H_ACROTERE = 6.20

# Grille structurelle
FILES_X = {"A": 0.15, "B": 4.95, "C": 7.45, "D": 11.85}
FILES_Y = {"1": 0.15, "2": 5.75, "3": 8.85}
POTEAUX = [(x, y) for y in FILES_Y.values() for x in FILES_X.values()]

EPA_POT = 0.30
EPA_POUTRE = 0.30
H_POUTRE = 0.40
EPA_SEM = 1.20
H_SEM = 0.30
EPA_LONGRINE = 0.20
H_LONGRINE = 0.30

# Murs extérieurs : (début, fin) des trous sur chaque côté
TROUS_SUD   = [(0.80, 2.60), (3.20, 4.60), (5.60, 6.60)]
TROUS_NORD  = [(1.20, 3.40), (7.90, 10.00)]
TROUS_OUEST = [(1.20, 3.40), (6.40, 8.00)]
TROUS_EST   = [(1.20, 3.40), (6.40, 8.00)]

# Cloisons intérieures
CLOISONS_V = [4.95, 7.45]
CLOISONS_H = [5.75]

# ============================================================ OUTILS
def nouveau_doc():
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 6
    return doc, doc.modelspace()

def setup_calques(doc):
    calques = [
        ("AXES", 1), ("MURS_EXT", 7), ("MURS_INT", 8),
        ("POTEAUX", 5), ("POUTRES", 6), ("DALLE", 9),
        ("SEMELLES", 1), ("LONGRINES", 2), ("FERRAILLAGE", 1),
        ("ELEC_ECLAIRAGE", 2), ("ELEC_PRISES", 5), ("ELEC_COURANTS", 6),
        ("PLOMB_EF", 5), ("PLOMB_EC", 1), ("PLOMB_EVAC", 3),
        ("SANITAIRE", 4), ("TEXTE", 2), ("COTES", 1),
        ("HACHURES", 8), ("DETAIL", 7), ("COTATION", 4),
    ]
    for n, c in calques:
        doc.layers.add(n, color=c)

def rect(msp, x1, y1, x2, y2, calque):
    msp.add_lwpolyline([(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
                       close=True, dxfattribs={"layer": calque})

def ligne(msp, x1, y1, x2, y2, calque):
    msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": calque})

def cercle(msp, x, y, r, calque):
    msp.add_circle((x, y), r, dxfattribs={"layer": calque})

def texte(msp, x, y, txt, h=0.20, calque="TEXTE", align="MIDDLE_CENTER"):
    if isinstance(txt, str): txt = [txt]
    for i, s in enumerate(txt):
        t = msp.add_text(s, height=h, dxfattribs={"layer": calque})
        t.set_placement((x, y - i * h * 1.4),
                        align=getattr(TextEntityAlignment, align))

def _decoupe(bornes, trous):
    for (a, b) in sorted(trous):
        out = []
        for (c, d) in bornes:
            if b <= c or a >= d: out.append((c, d))
            else:
                if c < a: out.append((c, a))
                if b < d: out.append((b, d))
        bornes = out
    return bornes

def mur_h(msp, x1, x2, y, ep, trous, calque):
    for (a, b) in _decoupe([(x1, x2)], trous):
        if b - a > 1e-6:
            rect(msp, a, y - ep/2, b, y + ep/2, calque)

def mur_v(msp, y1, y2, x, ep, trous, calque):
    for (a, b) in _decoupe([(y1, y2)], trous):
        if b - a > 1e-6:
            rect(msp, x - ep/2, a, x + ep/2, b, calque)

def axes(msp):
    for nom, x in FILES_X.items():
        msp.add_line((x, -1.0), (x, 10.0),
                     dxfattribs={"layer": "AXES", "linetype": "DASHED"})
        cercle(msp, x, -1.30, 0.35, "AXES")
        texte(msp, x, -1.30, nom, 0.30, "AXES")
    for nom, y in FILES_Y.items():
        msp.add_line((-1.0, y), (13.0, y),
                     dxfattribs={"layer": "AXES", "linetype": "DASHED"})
        cercle(msp, -1.30, y, 0.35, "AXES")
        texte(msp, -1.30, y, nom, 0.30, "AXES")

def trace_murs_ext(msp):
    mur_h(msp, 0.00, LX, 0.15, EP_EXT, TROUS_SUD,   "MURS_EXT")
    mur_h(msp, 0.00, LX, 8.85, EP_EXT, TROUS_NORD,  "MURS_EXT")
    mur_v(msp, 0.30, 8.70, 0.15, EP_EXT, TROUS_OUEST, "MURS_EXT")
    mur_v(msp, 0.30, 8.70, 11.85, EP_EXT, TROUS_EST, "MURS_EXT")

def trace_cloisons(msp):
    for x in CLOISONS_V:
        mur_v(msp, 0.30, 8.70, x, EP_INT, [], "MURS_INT")
    for y in CLOISONS_H:
        mur_h(msp, 0.30, 11.70, y, EP_INT, [], "MURS_INT")

def tableau(msp, x, y, titre, notes):
    """Cartouche + notes en bas de planche."""
    texte(msp, x, y, titre, 0.35, "TEXTE")
    for i, n in enumerate(notes):
        texte(msp, x, y - 0.55 - i * 0.35, n, 0.18, "TEXTE", "MIDDLE_LEFT")

# ============================================================ PE-01 FONDATIONS
def planche_fondations():
    doc, msp = nouveau_doc()
    setup_calques(doc)

    # Axes
    axes(msp)

    # Murs extérieurs en trait fin (repère)
    trace_murs_ext(msp)
    trace_cloisons(msp)

    # Semelles isolées sous poteaux : 1.20 x 1.20
    for (cx, cy) in POTEAUX:
        rect(msp, cx-EPA_SEM/2, cy-EPA_SEM/2,
                  cx+EPA_SEM/2, cy+EPA_SEM/2, "SEMELLES")
        # Hachures croisées symboliques
        for k in range(-5, 6):
            ligne(msp, cx-0.55+k*0.10, cy-0.55,
                       cx-0.45+k*0.10, cy+0.55, "HACHURES")
        texte(msp, cx, cy, "S", 0.20, "SEMELLES")

    # Semelles filantes sous murs extérieurs (0.60 x 0.30)
    def filante_h(x1, x2, y):
        rect(msp, x1, y-0.30, x2, y+0.30, "SEMELLES")
    def filante_v(y1, y2, x):
        rect(msp, x-0.30, y1, x+0.30, y2, "SEMELLES")
    filante_h(0.00, LX, 0.15)
    filante_h(0.00, LX, 8.85)
    filante_v(0.30, 8.70, 0.15)
    filante_v(0.30, 8.70, 11.85)

    # Longrines 0.20x0.30 entre semelles (sur axes)
    for x in FILES_X.values():
        ligne(msp, x-0.10, 0.30, x+0.10, 8.70, "LONGRINES")
    for y in FILES_Y.values():
        ligne(msp, 0.30, y-0.10, 11.70, y+0.10, "LONGRINES")

    # Amorces poteaux (0.30x0.30) - carré avec croix
    for (cx, cy) in POTEAUX:
        rect(msp, cx-0.15, cy-0.15, cx+0.15, cy+0.15, "POTEAUX")
        ligne(msp, cx-0.15, cy-0.15, cx+0.15, cy+0.15, "POTEAUX")
        ligne(msp, cx-0.15, cy+0.15, cx+0.15, cy-0.15, "POTEAUX")

    # Tableau poteaux + nomenclature
    y0 = -3.20
    texte(msp, 6, y0, "PLANCHE PE-01  -  PLAN DE FONDATIONS", 0.40)
    notes = [
        "NOMENCLATURE :",
        " - Semelles isolees S : 1.20 x 1.20 x 0.30 m  (12 u.)",
        " - Semelles filantes SF : 0.60 x 0.30 m  sous murs ext.",
        " - Longrines LR : 0.20 x 0.30 m  entre semelles",
        " - Poteaux BA : 0.30 x 0.30 m",
        "",
        "SPECIFICATIONS :",
        " - Beton de fondation : C25/30  -  Classe XC2",
        " - Acier : B500B  -  Enrobage 40 mm",
        " - Sol : portance minimale 2.0 bars (a verifier etude geotech.)",
        " - Ferraillage semelle : treillis ST25C + cadres HA8",
        " - Ferraillage poteau : 4 HA12 + etriers HA6 e=15 cm",
        " - Ferraillage longrine : 4 HA10 + etriers HA6 e=20 cm",
        " - Vide sanitaire 40 cm  -  Dallage BA 12 cm + polyane",
    ]
    tableau(msp, -1.0, y0-0.7, "", [])
    for i, n in enumerate(notes):
        texte(msp, -1.0, y0-0.7-i*0.30, n, 0.18, "TEXTE", "MIDDLE_LEFT")

    doc.saveas("PE-01-FONDATIONS.dxf")
    print("PE-01-FONDATIONS.dxf genere.")

# ============================================================ PE-02 COFFRAGE RDC
def planche_coffrage_rdc():
    doc, msp = nouveau_doc()
    setup_calques(doc)
    axes(msp)
    trace_murs_ext(msp)

    # Poteaux BA 0.30x0.30 (carré plein)
    for (cx, cy) in POTEAUX:
        rect(msp, cx-0.15, cy-0.15, cx+0.15, cy+0.15, "POTEAUX")
        cercle(msp, cx, cy, 0.05, "POTEAUX")

    # Poutres porteuses (traits doubles)
    # Poutres 30x40 : Y=0.15 et Y=8.85, X=0.15 et X=11.85, Y=5.75
    def poutre_h(y, x1=0, x2=LX):
        ligne(msp, x1, y-0.15, x2, y-0.15, "POUTRES")
        ligne(msp, x1, y+0.15, x2, y+0.15, "POUTRES")
    def poutre_v(x, y1=0, y2=LY):
        ligne(msp, x-0.15, y1, x-0.15, y2, "POUTRES")
        ligne(msp, x+0.15, y1, x+0.15, y2, "POUTRES")

    poutre_h(0.15); poutre_h(8.85); poutre_h(5.75)
    poutre_v(0.15); poutre_v(11.85)

    # Sens de portée dalle (hourdis 16+4)
    for i in range(20):
        x = 0.50 + i * 0.60
        ligne(msp, x, 0.30, x, 5.60, "DALLE")
        ligne(msp, x, 5.90, x, 8.70, "DALLE")

    # Treillis / repère hourdis
    texte(msp, 6, 3.00, "DALLE HOURDIS 16+4 = 20 cm", 0.25, "DALLE")
    texte(msp, 6, 7.20, "DALLE HOURDIS 16+4 = 20 cm", 0.25, "DALLE")

    # Escalier (trémie 2.40 x 2.40 à x=5.00, y=3.30)
    rect(msp, 5.00, 3.30, 7.40, 5.70, "DALLE")
    texte(msp, 6.20, 4.50, "TREMIE ESC.", 0.22, "DALLE")

    # Tableau
    y0 = -3.20
    texte(msp, 6, y0, "PLANCHE PE-02  -  COFFRAGE RDC", 0.40)
    notes = [
        "STRUCTURE PORTEUSE :",
        " - Poteaux BA 30x30 - 4 HA12 + etriers HA6 e=15",
        " - Poutres principales 30x40 (Y=0.15, Y=8.85, Y=5.75)",
        " - Poutres de rive 30x40 (X=0.15, X=11.85)",
        " - Dalle hourdis 16+4 = 20 cm, portee max 5.0 m",
        " - Treillis de repartition ST10C sur hourdis",
        "",
        "SPECIFICATIONS BETON :",
        " - C25/30  -  XC1  -  Classe d'exposition interieure",
        " - Enrobage 30 mm  -  Acier B500B",
        " - Coffrage : panneaux CTBX  -  Etaiement 2 niveaux",
        " - Cure beton 7 jours  -  Depuis coffrage 21 j avant charge",
    ]
    for i, n in enumerate(notes):
        texte(msp, -1.0, y0-0.7-i*0.30, n, 0.18, "TEXTE", "MIDDLE_LEFT")

    doc.saveas("PE-02-COFFRAGE-RDC.dxf")
    print("PE-02-COFFRAGE-RDC.dxf genere.")

# ============================================================ PE-03 COFFRAGE ETAGE
def planche_coffrage_etage():
    doc, msp = nouveau_doc()
    setup_calques(doc)
    axes(msp)
    trace_murs_ext(msp)

    # Poteaux etage (meme grille)
    for (cx, cy) in POTEAUX:
        rect(msp, cx-0.15, cy-0.15, cx+0.15, cy+0.15, "POTEAUX")
        cercle(msp, cx, cy, 0.05, "POTEAUX")

    # Poutres
    def poutre_h(y, x1=0, x2=LX):
        ligne(msp, x1, y-0.15, x2, y-0.15, "POUTRES")
        ligne(msp, x1, y+0.15, x2, y+0.15, "POUTRES")
    def poutre_v(x, y1=0, y2=LY):
        ligne(msp, x-0.15, y1, x-0.15, y2, "POUTRES")
        ligne(msp, x+0.15, y1, x+0.15, y2, "POUTRES")
    poutre_h(0.15); poutre_h(8.85); poutre_h(5.75)
    poutre_v(0.15); poutre_v(11.85)

    # Trémie escalier (2.40 x 2.40, position identique)
    rect(msp, 5.00, 3.30, 7.40, 5.70, "DALLE")
    # Marches
    for k in range(1, 7):
        yy = 3.30 + k * 0.26
        ligne(msp, 5.00, yy, 6.05, yy, "DALLE")
        ligne(msp, 6.35, yy, 7.40, yy, "DALLE")
    texte(msp, 6.20, 4.50, "ESCALIER", 0.20, "DALLE")

    # Acrotère périphérique 40 cm
    ligne(msp, -0.20, -0.20, LX+0.20, -0.20, "MURS_EXT")
    ligne(msp, -0.20, -0.20, -0.20, LY+0.20, "MURS_EXT")
    ligne(msp, -0.20, LY+0.20, LX+0.20, LY+0.20, "MURS_EXT")
    ligne(msp, LX+0.20, -0.20, LX+0.20, LY+0.20, "MURS_EXT")
    texte(msp, 6, -0.70, "ACROTERE PERIPHERIQUE h=0.40  -  Toiture-terrasse", 0.22)

    # Pentes toiture (2%)
    for i in range(15):
        y = 0.50 + i * 0.60
        ligne(msp, 0.30, y, 11.70, y, "HACHURES")

    # Tableau
    y0 = -3.20
    texte(msp, 6, y0, "PLANCHE PE-03  -  COFFRAGE ETAGE + TOITURE", 0.40)
    notes = [
        "STRUCTURE ETAGE :",
        " - Reprise identique RDC  -  Poteaux 30x30",
        " - Poutres 30x40  -  Dalle hourdis 16+4 = 20 cm",
        " - Tremie escalier 2.40 x 2.40 m  -  Garde-corps h=1.00",
        "",
        "TOITURE-TERRASSE :",
        " - Forme de pente : beton allege 1.5%",
        " - Etancheite bicouche elastomere  -  Releve 15 cm",
        " - Protection gravillon  -  Acrotere 0.40 m",
        " - Descentes EP : 4 x DN80 (angles)",
        " - Trop-plein 1 par facade",
    ]
    for i, n in enumerate(notes):
        texte(msp, -1.0, y0-0.7-i*0.30, n, 0.18, "TEXTE", "MIDDLE_LEFT")

    doc.saveas("PE-03-COFFRAGE-ETAGE.dxf")
    print("PE-03-COFFRAGE-ETAGE.dxf genere.")

# ============================================================ PE-04 ELECTRICITE
def symbole_plafond(msp, x, y):
    cercle(msp, x, y, 0.12, "ELEC_ECLAIRAGE")
    ligne(msp, x-0.12, y, x+0.12, y, "ELEC_ECLAIRAGE")
    ligne(msp, x, y-0.12, x, y+0.12, "ELEC_ECLAIRAGE")

def symbole_inter(msp, x, y):
    cercle(msp, x, y, 0.10, "ELEC_ECLAIRAGE")
    msp.add_arc(center=(x, y), radius=0.10, start_angle=0, end_angle=180,
                dxfattribs={"layer": "ELEC_ECLAIRAGE"})

def symbole_prise(msp, x, y):
    cercle(msp, x, y, 0.10, "ELEC_PRISES")
    ligne(msp, x-0.10, y, x+0.10, y, "ELEC_PRISES")
    ligne(msp, x, y-0.10, x, y+0.10, "ELEC_PRISES")

def symbole_rj(msp, x, y):
    rect(msp, x-0.10, y-0.10, x+0.10, y+0.10, "ELEC_COURANTS")
    ligne(msp, x-0.10, y, x+0.10, y, "ELEC_COURANTS")

def symbole_tv(msp, x, y):
    rect(msp, x-0.10, y-0.10, x+0.10, y+0.10, "ELEC_COURANTS")
    msp.add_arc(center=(x, y), radius=0.06, start_angle=0, end_angle=360,
                dxfattribs={"layer": "ELEC_COURANTS"})

def planche_electricite():
    doc, msp = nouveau_doc()
    setup_calques(doc)

    # === RDC ===
    trace_murs_ext(msp)
    trace_cloisons(msp)
    texte(msp, 6, 10.20, "ELECTRICITE - RDC", 0.45)

    # Points lumineux plafond
    points_rdc = [
        (2.5, 3.0), (2.5, 6.0),                      # sejour
        (9.5, 3.0), (9.5, 6.0),                      # cuisine/SAM
        (9.5, 7.5),                                   # bureau
        (2.5, 7.5),                                   # buanderie
        (6.2, 1.5), (6.2, 4.5), (6.8, 8.10),          # hall/esc/dégag
        (5.7, 6.5),                                   # WC
    ]
    for (x, y) in points_rdc:
        symbole_plafond(msp, x, y)

    # Interrupteurs (à 1.10 m du sol)
    inters_rdc = [(1.5, 1.0, "sejour"), (5.5, 1.0, "hall"),
                  (8.4, 1.0, "cuisine"), (8.4, 6.5, "SAM"),
                  (10.5, 7.5, "bureau"), (3.5, 7.5, "buanderie"),
                  (5.0, 6.5, "WC"), (5.0, 8.0, "dégag")]
    for (x, y, _) in inters_rdc:
        symbole_inter(msp, x, y)

    # Prises 16A/32A (à 0.30 m du sol)
    prises_rdc = [
        (1.0, 2.0), (1.0, 4.0), (4.0, 2.0), (4.0, 4.0),  # sejour
        (8.0, 2.0), (11.0, 2.0), (8.0, 5.5), (11.0, 5.5),  # cuisine
        (8.0, 7.5), (11.0, 7.5),                          # bureau
        (1.0, 7.5), (4.0, 7.5),                           # buanderie
        (5.5, 8.0), (7.0, 8.0),                           # dégagement
    ]
    for (x, y) in prises_rdc:
        symbole_prise(msp, x, y)

    # RJ45 / TV
    for (x, y) in [(2.5, 1.0), (9.5, 1.0)]:
        symbole_rj(msp, x, y)
    for (x, y) in [(3.5, 1.0), (8.5, 1.0)]:
        symbole_tv(msp, x, y)

    # Tableau électrique + arrivée ERDF
    rect(msp, 5.30, 0.10, 5.90, 0.40, "ELEC_COURANTS")
    texte(msp, 5.60, 0.90, "TGBT", 0.18, "ELEC_COURANTS")

    # === ETAGE (décalé à droite) ===
    dx = 14.00
    for poly in [  # décalage simple : on redessine tout
    ]: pass
    # Murs décalés
    def dep_h(x1, x2, y, trous):
        for (a, b) in _decoupe([(x1, x2)], trous):
            ligne(msp, a+dx, y, b+dx, y, "MURS_EXT")
        ligne(msp, x1+dx, y, x2+dx, y, "MURS_EXT")
    def dep_v(y1, y2, x, trous):
        for (a, b) in _decoupe([(y1, y2)], trous):
            ligne(msp, x+dx, a, x+dx, b, "MURS_EXT")

    dep_h(0, LX, 0.00, TROUS_SUD)
    dep_h(0, LX, 9.00, TROUS_NORD)
    dep_v(0, 9, 0.00, TROUS_OUEST)
    dep_v(0, 9, 12.00, TROUS_EST)
    for x in CLOISONS_V:
        ligne(msp, x+dx, 0.30, x+dx, 8.70, "MURS_INT")
    ligne(msp, 0.30+dx, 5.75, 11.70+dx, 5.75, "MURS_INT")
    ligne(msp, 2.65+dx, 0.30, 2.65+dx, 2.65, "MURS_INT")
    ligne(msp, 2.70+dx, 2.65, 4.90+dx, 2.65, "MURS_INT")

    texte(msp, 6+dx, 10.20, "ELECTRICITE - ETAGE", 0.45)

    # Points lumineux étage
    pts_et = [
        (2.5, 6.5), (1.4, 2.5),               # chambres 1, 2
        (3.9, 1.5),                            # SDB 1
        (3.9, 3.7),                            # dégagement
        (9.5, 7.5), (9.5, 4.5),                # ch. 3, 4
        (9.5, 1.5),                            # salle d'eau
        (6.2, 1.5), (6.2, 4.5), (6.2, 7.5),    # couloir/palier/dégag
    ]
    for (x, y) in pts_et:
        symbole_plafond(msp, x+dx, y)

    # Interrupteurs étage
    for (x, y) in [(1.5, 6.5), (1.5, 2.5), (4.5, 1.5), (4.5, 3.7),
                   (8.4, 7.5), (8.4, 4.5), (8.4, 1.5),
                   (5.0, 1.5), (5.0, 4.5), (5.0, 7.5)]:
        symbole_inter(msp, x+dx, y)

    # Prises étage
    for (x, y) in [
        (1.0, 6.0), (1.0, 7.5), (4.0, 6.0), (4.0, 7.5),   # ch. 1
        (1.0, 1.5), (1.0, 3.5),                             # ch. 2
        (2.0, 1.0), (4.5, 1.0),                             # SDB
        (8.0, 7.5), (11.0, 7.5),                            # ch. 3
        (8.0, 4.5), (11.0, 4.5),                            # ch. 4
        (8.0, 1.5), (11.0, 1.5),                            # salle d'eau
    ]:
        symbole_prise(msp, x+dx, y)

    # RJ45 / TV étage
    for (x, y) in [(2.5+dx, 7.5), (2.5+dx, 1.5), (9.5+dx, 7.5), (9.5+dx, 1.5)]:
        symbole_rj(msp, x, y)
    for (x, y) in [(3.5+dx, 7.5), (9.5+dx, 4.5)]:
        symbole_tv(msp, x, y)

    # Tableau divisionnaire étage
    rect(msp, 5.30+dx, 4.10, 5.90+dx, 4.40, "ELEC_COURANTS")
    texte(msp, 5.60+dx, 4.90, "TD ETAGE", 0.18, "ELEC_COURANTS")

    # Légende
    y0 = -1.20
    texte(msp, 2, y0, "LEGENDE :", 0.30, "TEXTE", "MIDDLE_LEFT")
    symbole_plafond(msp, 4.00, y0)
    texte(msp, 4.60, y0, "Point lumineux plafond", 0.20, "TEXTE", "MIDDLE_LEFT")
    symbole_inter(msp, 4.00, y0-0.50)
    texte(msp, 4.60, y0-0.50, "Interrupteur 1.10 m", 0.20, "TEXTE", "MIDDLE_LEFT")
    symbole_prise(msp, 4.00, y0-1.00)
    texte(msp, 4.60, y0-1.00, "Prise 2P+T 16A  -  0.30 m", 0.20, "TEXTE", "MIDDLE_LEFT")
    symbole_rj(msp, 4.00, y0-1.50)
    texte(msp, 4.60, y0-1.50, "Prise RJ45  -  0.30 m", 0.20, "TEXTE", "MIDDLE_LEFT")
    symbole_tv(msp, 4.00, y0-2.00)
    texte(msp, 4.60, y0-2.00, "Prise TV coaxiale", 0.20, "TEXTE", "MIDDLE_LEFT")

    # Tableau protections
    y0 = -4.50
    texte(msp, 6, y0, "PLANCHE PE-04  -  INSTALLATION ELECTRIQUE", 0.40)
    notes = [
        "TABLEAU TGBT - RDC (12 modules) + TD ETAGE :",
        "  C1  Eclairage RDC ............... 10A  -  1.5 mm2",
        "  C2  Prises sejour + hall ........ 16A  -  2.5 mm2",
        "  C3  Prises cuisine (plan travail) 20A  -  2.5 mm2",
        "  C4  Plaques cuisson .............. 32A  -  6 mm2",
        "  C5  Four + LV .................... 20A  -  2.5 mm2",
        "  C6  Buanderie (LL, SL) ........... 20A  -  2.5 mm2",
        "  C7  Eclairage etage .............. 10A  -  1.5 mm2",
        "  C8  Prises chambres .............. 16A  -  2.5 mm2",
        "  C9  Chauffe-eau .................. 20A  -  2.5 mm2",
        "  C10 VMC simple flux .............. 2A   -  1.5 mm2",
        "  Interrupteur differentiel 30 mA type AC + type A",
        "  Parafoudre type 2  -  Terre unique < 10 ohm",
    ]
    for i, n in enumerate(notes):
        texte(msp, -1.0, y0-0.7-i*0.28, n, 0.17, "TEXTE", "MIDDLE_LEFT")

    doc.saveas("PE-04-ELECTRICITE.dxf")
    print("PE-04-ELECTRICITE.dxf genere.")

# ============================================================ PE-05 PLOMBERIE
def sym_wc(msp, x, y):
    rect(msp, x-0.20, y-0.30, x+0.20, y+0.30, "SANITAIRE")
    cercle(msp, x, y+0.15, 0.15, "SANITAIRE")
def sym_lav(msp, x, y):
    rect(msp, x-0.25, y-0.20, x+0.25, y+0.20, "SANITAIRE")
    cercle(msp, x, y, 0.06, "SANITAIRE")
def sym_baignoire(msp, x, y):
    rect(msp, x-0.85, y-0.35, x+0.85, y+0.35, "SANITAIRE")
    cercle(msp, x-0.65, y, 0.06, "SANITAIRE")
def sym_douche(msp, x, y):
    rect(msp, x-0.45, y-0.45, x+0.45, y+0.45, "SANITAIRE")
    cercle(msp, x, y, 0.08, "SANITAIRE")
def sym_evier(msp, x, y):
    rect(msp, x-0.50, y-0.30, x+0.50, y+0.30, "SANITAIRE")
    cercle(msp, x-0.25, y, 0.10, "SANITAIRE")
    cercle(msp, x+0.25, y, 0.10, "SANITAIRE")
def sym_ll(msp, x, y):
    rect(msp, x-0.30, y-0.30, x+0.30, y+0.30, "SANITAIRE")
    cercle(msp, x, y, 0.18, "SANITAIRE")
def sym_ce(msp, x, y):
    cercle(msp, x, y, 0.30, "SANITAIRE")
    texte(msp, x, y, "CE", 0.15, "SANITAIRE")

def planche_plomberie():
    doc, msp = nouveau_doc()
    setup_calques(doc)

    # === RDC ===
    trace_murs_ext(msp)
    trace_cloisons(msp)
    texte(msp, 6, 10.20, "PLOMBERIE - RDC", 0.45)

    # Appareils sanitaires RDC
    sym_wc(msp, 5.70, 6.80)              # WC
    sym_evier(msp, 9.00, 6.50)           # cuisine - évier sous fenêtre
    sym_ll(msp, 1.50, 7.50)              # buanderie - lave-linge
    sym_ll(msp, 2.50, 7.50)              # sèche-linge
    sym_ce(msp, 1.00, 7.50)              # chauffe-eau

    # Amenée EF (froid) - bleu : depuis nourrice
    # Nourrice au niveau buanderie
    rect(msp, 2.90, 6.90, 3.40, 7.20, "PLOMB_EF")
    texte(msp, 3.15, 6.50, "Nourrice EF", 0.15, "PLOMB_EF")
    # Réseau EF
    for (xa, ya, xb, yb) in [
        (3.15, 6.90, 3.15, 7.20), (3.15, 7.20, 5.70, 7.20), (5.70, 7.20, 5.70, 6.80),
        (3.15, 7.20, 9.00, 7.20), (9.00, 7.20, 9.00, 6.80),
        (3.15, 7.20, 1.50, 7.20), (3.15, 7.20, 2.50, 7.20),
        (3.15, 6.90, 3.15, 3.00), (3.15, 3.00, 5.60, 3.00),
    ]:
        ligne(msp, xa, ya, xb, yb, "PLOMB_EF")

    # Amenée EC (chaude) - rouge : depuis chauffe-eau
    for (xa, ya, xb, yb) in [
        (1.30, 7.20, 5.70, 7.20), (5.70, 7.20, 5.70, 6.80),
        (1.30, 7.20, 9.00, 7.20), (9.00, 7.20, 9.00, 6.80),
        (1.30, 7.20, 1.30, 3.00), (1.30, 3.00, 5.60, 3.00),
    ]:
        ligne(msp, xa, ya, xb, yb, "PLOMB_EC")

    # Évacuation EU/EV - vert
    for (xa, ya, xb, yb) in [
        (5.70, 6.80, 5.70, 5.00), (5.70, 5.00, 5.70, 4.00),
        (5.70, 4.00, 3.00, 4.00), (3.00, 4.00, 3.00, 0.30),
        (9.00, 6.50, 9.00, 5.00), (9.00, 5.00, 9.00, 4.00),
        (9.00, 4.00, 7.50, 4.00), (7.50, 4.00, 7.50, 0.30),
        (1.50, 7.50, 1.50, 4.00),
    ]:
        ligne(msp, xa, ya, xb, yb, "PLOMB_EVAC")
    # Attente EV dans dalle
    texte(msp, 3.00, 0.80, "EV DN100 → reseau", 0.15, "PLOMB_EVAC")

    # === ETAGE (décalé) ===
    dx = 14.00
    dep_trous_sud  = [(1.20, 2.80), (3.40, 4.60)]
    dep_trous_nord = [(1.20, 3.40), (5.60, 7.00), (8.20, 10.00)]
    dep_trous_o    = [(1.00, 3.00), (6.20, 8.00)]
    dep_trous_e    = [(1.00, 3.00), (6.20, 8.00)]

    for (a, b) in _decoupe([(0, LX)], dep_trous_sud):
        ligne(msp, a+dx, 0.00, b+dx, 0.00, "MURS_EXT")
    for (a, b) in _decoupe([(0, LX)], dep_trous_nord):
        ligne(msp, a+dx, 9.00, b+dx, 9.00, "MURS_EXT")
    for (a, b) in _decoupe([(0, LY)], dep_trous_o):
        ligne(msp, 0.00+dx, a, 0.00+dx, b, "MURS_EXT")
    for (a, b) in _decoupe([(0, LY)], dep_trous_e):
        ligne(msp, 12.00+dx, a, 12.00+dx, b, "MURS_EXT")

    for x in CLOISONS_V:
        ligne(msp, x+dx, 0.30, x+dx, 8.70, "MURS_INT")
    ligne(msp, 0.30+dx, 5.75, 11.70+dx, 5.75, "MURS_INT")
    ligne(msp, 0.30+dx, 4.85, 4.90+dx, 4.85, "MURS_INT")
    ligne(msp, 2.65+dx, 0.30, 2.65+dx, 4.80, "MURS_INT")
    ligne(msp, 2.70+dx, 2.65, 4.90+dx, 2.65, "MURS_INT")
    ligne(msp, 7.50+dx, 0.30, 7.50+dx, 3.25, "MURS_INT")
    ligne(msp, 7.50+dx, 3.25, 11.70+dx, 3.25, "MURS_INT")

    texte(msp, 6+dx, 10.20, "PLOMBERIE - ETAGE", 0.45)

    # Appareils étage
    sym_lav(msp, 3.60+dx, 0.90)          # SDB 1 - lavabo
    sym_baignoire(msp, 3.60+dx, 1.90)    # SDB 1 - baignoire
    sym_douche(msp, 9.50+dx, 0.90)       # salle d'eau - douche
    sym_lav(msp, 10.70+dx, 1.80)         # salle d'eau - lavabo
    sym_ll(msp, 9.50+dx, 2.70)           # salle d'eau - lave-linge

    # EF etage
    for (xa, ya, xb, yb) in [
        (3.90+dx, 6.90, 3.90+dx, 3.90), (3.90+dx, 3.90, 3.60+dx, 3.90),
        (3.60+dx, 3.90, 3.60+dx, 2.20),
        (3.90+dx, 3.90, 6.20+dx, 3.90), (6.20+dx, 3.90, 6.20+dx, 3.00),
        (6.20+dx, 3.00, 9.90+dx, 3.00), (9.90+dx, 3.00, 9.90+dx, 2.20),
    ]:
        ligne(msp, xa, ya, xb, yb, "PLOMB_EF")

    # EC etage
    for (xa, ya, xb, yb) in [
        (3.90+dx, 6.90, 3.90+dx, 2.10),
        (3.90+dx, 2.10, 3.60+dx, 2.10),
        (3.90+dx, 3.90, 9.90+dx, 3.90), (9.90+dx, 3.90, 9.90+dx, 2.10),
    ]:
        ligne(msp, xa, ya, xb, yb, "PLOMB_EC")

    # Évacuation etage
    for (xa, ya, xb, yb) in [
        (3.60+dx, 2.20, 3.60+dx, 0.90), (3.60+dx, 0.90, 4.60+dx, 0.90),
        (4.60+dx, 0.90, 4.60+dx, 2.50),
        (4.60+dx, 2.50, 4.95+dx, 2.50), (4.95+dx, 2.50, 4.95+dx, 5.60),
        (9.50+dx, 0.90, 9.50+dx, 2.20), (9.50+dx, 2.20, 10.70+dx, 2.20),
        (10.70+dx, 2.20, 10.70+dx, 3.80), (10.70+dx, 3.80, 7.50+dx, 3.80),
        (7.50+dx, 3.80, 7.50+dx, 5.60), (7.50+dx, 5.60, 4.95+dx, 5.60),
    ]:
        ligne(msp, xa, ya, xb, yb, "PLOMB_EVAC")

    # Légende
    y0 = -1.20
    texte(msp, 2, y0, "LEGENDE :", 0.30, "TEXTE", "MIDDLE_LEFT")
    ligne(msp, 3.50, y0, 4.50, y0, "PLOMB_EF")
    texte(msp, 4.70, y0, "Alimentation eau froide (EF) - PER DN16", 0.20, "TEXTE", "MIDDLE_LEFT")
    ligne(msp, 3.50, y0-0.50, 4.50, y0-0.50, "PLOMB_EC")
    texte(msp, 4.70, y0-0.50, "Alimentation eau chaude (EC) - PER DN16", 0.20, "TEXTE", "MIDDLE_LEFT")
    ligne(msp, 3.50, y0-1.00, 4.50, y0-1.00, "PLOMB_EVAC")
    texte(msp, 4.70, y0-1.00, "Evacuation EU/EV - PVC DN32 a DN100", 0.20, "TEXTE", "MIDDLE_LEFT")
    y0 -= 1.80
    texte(msp, 2, y0, "APPAREILS :", 0.30, "TEXTE", "MIDDLE_LEFT")
    sym_wc(msp, 4.00, y0); texte(msp, 4.60, y0, "WC", 0.20, "TEXTE", "MIDDLE_LEFT")
    sym_lav(msp, 6.50, y0); texte(msp, 7.20, y0, "Lavabo", 0.20, "TEXTE", "MIDDLE_LEFT")
    sym_douche(msp, 9.50, y0); texte(msp, 10.20, y0, "Douche", 0.20, "TEXTE", "MIDDLE_LEFT")
    sym_baignoire(msp, 13.0, y0); texte(msp, 14.20, y0, "Baignoire", 0.20, "TEXTE", "MIDDLE_LEFT")

    # Tableau
    y0 = -4.50
    texte(msp, 6, y0, "PLANCHE PE-05  -  RESEAUX PLOMBERIE", 0.40)
    notes = [
        "ALIMENTATION :",
        "  - Reseau EF depuis compteur -> nourrice 3/4",
        "  - Distribution en PER DN16 sous fourreau",
        "  - Chauffe-eau 200 L electrique - buanderie RDC",
        "  - Pression : 2.5 bars  -  Reduction 3 bars si > 4",
        "",
        "EVACUATIONS :",
        "  - EU/EV : PVC-U DN32 a DN100  -  Pente 2 cm/m mini",
        "  - Chute unique verticale DN100 - colonne EO",
        "  - Ventilation primaire DN100 en toiture",
        "  - EP pluviales : 4 descentes DN80 + trop-plein",
        "  - Regard de visite 40x40 sous dalle RDC",
        "",
        "ETANCHEITE SDB :",
        "  - SPEC (systeme d'etancheite liquide) sous carrelage",
        "  - Releves 15 cm  -  Cuvette 5 cm",
    ]
    for i, n in enumerate(notes):
        texte(msp, -1.0, y0-0.7-i*0.28, n, 0.17, "TEXTE", "MIDDLE_LEFT")

    doc.saveas("PE-05-PLOMBERIE.dxf")
    print("PE-05-PLOMBERIE.dxf genere.")

# ============================================================ PE-06 COUPES + DETAILS
def planche_coupes():
    doc, msp = nouveau_doc()
    setup_calques(doc)

    # ======== COUPE AA (longitudinale, 12 m) ========
    ox, oy = 0.0, 0.0
    ep_hachure = 0.05

    # Fondation - semelle filante enterree
    rect(msp, ox+0.00, oy-0.70, ox+0.60, oy-0.40, "DETAIL")
    rect(msp, ox+0.00, oy-0.40, ox+0.30, oy+0.00, "DETAIL")
    texte(msp, ox+0.30, oy-0.80, "Semelle filante 60x30", 0.15, "TEXTE", "MIDDLE_LEFT")

    # Vide sanitaire + dallage
    ligne(msp, ox, oy, ox+LX, oy, "DETAIL")
    rect(msp, ox, oy+0.00, ox+LX, oy+0.20, "DALLE")   # dallage BA 20
    texte(msp, ox+6, oy+0.10, "Dallage BA 20 cm", 0.15, "DALLE")

    # Murs RDC et étage (deux traits verticaux + vides)
    y_rdc_sol = 0.20
    y_rdc_plaf = y_rdc_sol + 2.80
    y_etage_sol = y_rdc_plaf + 0.20   # dalle 20
    y_etage_plaf = y_etage_sol + 2.80
    y_acrotere = y_etage_plaf + 0.40

    # Murs extérieurs (0.30 épaisseur)
    for x in [ox, ox+LX-0.30]:
        rect(msp, x, y_rdc_sol, x+0.30, y_etage_plaf, "MURS_EXT")
    # Acrotère
    rect(msp, ox, y_etage_plaf, ox+0.30, y_acrotere, "MURS_EXT")
    rect(msp, ox+LX-0.30, y_etage_plaf, ox+LX, y_acrotere, "MURS_EXT")

    # Dalle étage (hourdis 20)
    rect(msp, ox, y_rdc_plaf, ox+LX, y_etage_sol, "DALLE")
    # Dalle toiture (hourdis 20)
    rect(msp, ox, y_etage_plaf-0.20, ox+LX, y_etage_plaf, "DALLE")
    # Étanchéité + protection
    ligne(msp, ox-0.10, y_etage_plaf, ox+LX+0.10, y_etage_plaf, "DETAIL")
    ligne(msp, ox-0.10, y_etage_plaf+0.04, ox+LX+0.10, y_etage_plaf+0.04, "DETAIL")

    # Poteau intérieur
    rect(msp, ox+4.95-0.15, y_rdc_sol, ox+4.95+0.15, y_etage_plaf, "POTEAUX")

    # Ouvertures : porte entrée + fenêtres étage
    # Porte d'entrée (0.80-2.60)
    ligne(msp, ox+0.80, y_rdc_sol, ox+0.80, y_rdc_sol+2.20, "OUVERTURES")
    ligne(msp, ox+0.80, y_rdc_sol+2.20, ox+2.60, y_rdc_sol+2.20, "OUVERTURES")
    # Fenêtre étage
    rect(msp, ox+1.20, y_etage_sol+0.90, ox+2.80, y_etage_sol+2.30, "OUVERTURES")

    # Cotations
    msp.add_linear_dim(base=(0, -1.80), p1=(ox, 0), p2=(ox+LX, 0),
                       dxfattribs={"layer": "COTES"}).render()
    msp.add_linear_dim(base=(-1.20, 0), p1=(ox, 0), p2=(ox, y_acrotere),
                       angle=90, dxfattribs={"layer": "COTES"}).render()

    # Niveaux
    for y_niv, txt in [(0, "+0.00"), (y_rdc_plaf, "+2.80"), (y_etage_sol, "+3.00"),
                       (y_etage_plaf, "+5.80"), (y_acrotere, "+6.20")]:
        ligne(msp, ox-1.0, y_niv, ox+LX+0.5, y_niv, "COTES")
        texte(msp, ox-0.30, y_niv+0.10, txt, 0.15, "COTES", "MIDDLE_RIGHT")

    texte(msp, ox+LX/2, y_acrotere+1.0, "COUPE AA  -  LONGITUDINALE 12 m", 0.35)

    # ======== COUPE BB (transversale, 9 m) ========
    ox2 = 16.0
    for x in [ox2, ox2+LY-0.30]:
        rect(msp, x, y_rdc_sol, x+0.30, y_etage_plaf, "MURS_EXT")
    rect(msp, ox2, y_etage_plaf, ox2+0.30, y_acrotere, "MURS_EXT")
    rect(msp, ox2+LY-0.30, y_etage_plaf, ox2+LY, y_acrotere, "MURS_EXT")
    rect(msp, ox2, y_rdc_plaf, ox2+LY, y_etage_sol, "DALLE")
    rect(msp, ox2, y_etage_plaf-0.20, ox2+LY, y_etage_plaf, "DALLE")
    rect(msp, ox2, oy, ox2+LY, oy+0.20, "DALLE")
    # Poteau central (axe Y=5.75)
    rect(msp, ox2+5.75-0.15, y_rdc_sol, ox2+5.75+0.15, y_etage_plaf, "POTEAUX")
    # Escalier symbolique
    for k in range(8):
        x_esc = ox2+3.00 + k*0.28
        ligne(msp, x_esc, y_rdc_sol, x_esc, y_rdc_sol+0.17*k, "ESCALIER")

    texte(msp, ox2+LY/2, y_acrotere+1.0, "COUPE BB  -  TRANSVERSALE 9 m", 0.35)
    msp.add_linear_dim(base=(0, -1.80), p1=(ox2, 0), p2=(ox2+LY, 0),
                       dxfattribs={"layer": "COTES"}).render()
    msp.add_linear_dim(base=(ox2-1.20, 0), p1=(ox2, 0), p2=(ox2, y_acrotere),
                       angle=90, dxfattribs={"layer": "COTES"}).render()

    # ======== DÉTAILS ========
    # D1 - Détail fondation / poteau / longrine
    dx, dy = 0.0, -8.0
    texte(msp, dx+1.5, dy+3.5, "D1 - DETAIL FONDATION", 0.30)
    # Sol naturel
    ligne(msp, dx-1.0, dy+0.0, dx+4.0, dy+0.0, "DETAIL")
    for k in range(15):
        ligne(msp, dx-1.0+k*0.35, dy+0.0, dx-0.85+k*0.35, dy-0.20, "DETAIL")
    # Semelle
    rect(msp, dx+0.0, dy+0.0, dx+1.20, dy+0.30, "SEMELLES")
    # Treillis HA8 (pointillé)
    ligne(msp, dx+0.05, dy+0.10, dx+1.15, dy+0.10, "FERRAILLAGE")
    ligne(msp, dx+0.05, dy+0.20, dx+1.15, dy+0.20, "FERRAILLAGE")
    # Poteau
    rect(msp, dx+0.45, dy+0.30, dx+0.75, dy+1.60, "POTEAUX")
    # Armatures poteau
    for (ax, ay) in [(dx+0.50, dy+0.35), (dx+0.70, dy+0.35),
                     (dx+0.50, dy+1.55), (dx+0.70, dy+1.55)]:
        cercle(msp, ax, ay, 0.025, "FERRAILLAGE")
    for yy in [dy+0.40, dy+0.60, dy+0.80, dy+1.00, dy+1.20, dy+1.40]:
        ligne(msp, dx+0.50, yy, dx+0.70, yy, "FERRAILLAGE")
    # Longrine
    rect(msp, dx+0.75, dy+0.30, dx+1.80, dy+0.60, "LONGRINES")
    # Cotations
    msp.add_linear_dim(base=(dx+0.6, dy-0.60), p1=(dx+0.0, dy+0.0),
                       p2=(dx+1.20, dy+0.0),
                       dxfattribs={"layer": "COTES"}).render()
    msp.add_linear_dim(base=(dx+2.0, dy+0.0), p1=(dx+1.20, dy+0.0),
                       p2=(dx+1.20, dy+0.30), angle=90,
                       dxfattribs={"layer": "COTES"}).render()
    texte(msp, dx+0.60, dy-1.0, "1200", 0.15, "COTES")
    texte(msp, dx+2.3, dy+0.15, "300", 0.15, "COTES")

    # D2 - Détail acrotère / étanchéité
    dx2, dy2 = 6.0, -8.0
    texte(msp, dx2+1.5, dy2+3.5, "D2 - DETAIL ACROTERE", 0.30)
    # Dalle support
    rect(msp, dx2, dy2+0.0, dx2+2.5, dy2+0.20, "DALLE")
    # Forme de pente
    msp.add_lwpolyline([(dx2, dy2+0.20), (dx2+2.5, dy2+0.20),
                        (dx2+2.5, dy2+0.28), (dx2, dy2+0.45)],
                       close=True, dxfattribs={"layer": "DETAIL"})
    # Étanchéité
    ligne(msp, dx2, dy2+0.45, dx2+2.5, dy2+0.28, "DETAIL")
    ligne(msp, dx2, dy2+0.48, dx2+2.5, dy2+0.31, "DETAIL")
    # Acrotère (0.40) avec relevé
    rect(msp, dx2+2.30, dy2+0.20, dx2+2.50, dy2+0.60, "MURS_EXT")
    # Relevé étanchéité 15 cm
    ligne(msp, dx2+2.30, dy2+0.20, dx2+2.30, dy2+0.35, "DETAIL")
    # Protection gravillon
    for k in range(15):
        cercle(msp, dx2+0.10+k*0.15, dy2+0.52, 0.04, "HACHURES")
    texte(msp, dx2+1.0, dy2-0.40, "Forme de pente 1.5% + etancheite bicouche", 0.15)

    # D3 - Détail escalier (coupe)
    dx3, dy3 = 11.0, -8.0
    texte(msp, dx3+1.5, dy3+3.5, "D3 - DETAIL ESCALIER", 0.30)
    # Paillasse
    n_marches = 16
    h_m = 0.175
    l_m = 0.280
    x0, y0 = dx3, dy3
    points = [(x0, y0)]
    for k in range(n_marches):
        xa = x0 + k*l_m
        ya = y0 + k*h_m
        points.append((xa, ya + h_m))
        points.append((xa + l_m, ya + h_m))
    # Paillasse BA
    msp.add_lwpolyline([(p[0], p[1]-0.15) for p in points] +
                        [(p[0], p[1]) for p in reversed(points)],
                        close=True, dxfattribs={"layer": "ESCALIER"})
    # Ferraillage paillasse
    for k in range(0, len(points), 3):
        ligne(msp, points[k][0], points[k][1]-0.07,
              points[min(k+2, len(points)-1)][0], points[min(k+2, len(points)-1)][1]-0.07,
              "FERRAILLAGE")
    texte(msp, dx3+3, dy3-0.50, "Paillasse BA 15 cm - 16 marches 17.5 x 28 cm", 0.15)

    # D4 - Détail poteau + poutre (noeud)
    dx4, dy4 = 19.0, -8.0
    texte(msp, dx4+1.5, dy4+3.5, "D4 - NOEUD POTEAU / POUTRE", 0.30)
    # Poteau
    rect(msp, dx4+0.50, dy4+0.0, dx4+0.80, dy4+2.00, "POTEAUX")
    # Armatures poteau
    for yy in [dy4+0.10, dy4+0.40, dy4+0.70, dy4+1.00, dy4+1.30, dy4+1.60, dy4+1.90]:
        ligne(msp, dx4+0.55, yy, dx4+0.75, yy, "FERRAILLAGE")
    # Poutre
    rect(msp, dx4+0.00, dy4+1.60, dx4+2.50, dy4+2.00, "POUTRES")
    # Armatures poutre (chapeaux + lit inf)
    ligne(msp, dx4+0.05, dy4+1.90, dx4+2.45, dy4+1.90, "FERRAILLAGE")
    ligne(msp, dx4+0.05, dy4+1.70, dx4+2.45, dy4+1.70, "FERRAILLAGE")
    # Étriers
    for xx in [dx4+0.15 + k*0.20 for k in range(12)]:
        ligne(msp, xx, dy4+1.65, xx, dy4+1.95, "FERRAILLAGE")
    texte(msp, dx4+1.2, dy4-0.40, "4 HA12 + etriers HA6 e=15 - poutre 4 HA14", 0.15)

    # ======== CARTouche + NOTES ========
    texte(msp, 6, -12.20, "PLANCHE PE-06  -  COUPES & DETAILS CONSTRUCTIFS", 0.40)
    notes = [
        "NOTES GENERALES D'EXECUTION :",
        " 1. Toutes les dimensions sont en metres, sauf indication contraire.",
        " 2. Les niveaux sont exprimes en metres par rapport au sol fini (PM = +0.00).",
        " 3. Beton C25/30 pour toute la superstructure - XC1 interieur.",
        " 4. Aciers B500B - Enrobage : 40 mm (fondation), 30 mm (elevation).",
        " 5. Etaiement obligatoire sous poutres et dalles jusqu'a 21 j.",
        " 6. Etancheite toiture-terrasse : bicouche elastomere + protection gravillon.",
        " 7. VMC simple flux hygroreglable - reseau gaine isole.",
        " 8. Garde-corps escalier et palier : h=1.00 m, barreaudage vertical.",
        " 9. Ce dossier d'execution doit etre valide par :",
        "      - un bureau d'etudes structure agree (note de calcul)",
        "      - un architecte inscrit a l'Ordre (loi CAP 2016 si SP>150 m2)",
        "      - un bureau de controle (si ERP ou logement collectif)",
    ]
    for i, n in enumerate(notes):
        texte(msp, -1.0, -12.90-i*0.30, n, 0.17, "TEXTE", "MIDDLE_LEFT")

    doc.saveas("PE-06-COUPES-DETAILS.dxf")
    print("PE-06-COUPES-DETAILS.dxf genere.")

# ============================================================ MAIN
if __name__ == "__main__":
    planche_fondations()
    planche_coffrage_rdc()
    planche_coffrage_etage()
    planche_electricite()
    planche_plomberie()
    planche_coupes()
    print("\n6 fichiers DXF generes.")
    print("Convertir en DWG via AutoCAD ou ODA File Converter.")