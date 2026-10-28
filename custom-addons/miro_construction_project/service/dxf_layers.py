"""
Rôles de calque DXF et noms qui les désignent.

Un moteur d'analyse ne cherche pas un calque par son nom : il cherche un
RÔLE (« mur extérieur », « poteau »...). Le nom des calques varie d'un
bureau d'études à l'autre (« A-MUR-EXT », « MURS_EXT »...) ; il vient de la
configuration Odoo (conventions de calques, modèle
construction.dxf.layer.convention), transmise au moteur sous forme de
LayerConfig.

Ce module ne dépend pas d'Odoo : les moteurs restent testables seuls, avec
la configuration par défaut ci-dessous (celle livrée dans la convention
Miro).

Un nom peut contenir le joker « * » (« A-MUR-EXT* » reconnaît
« A-MUR-EXT-RDC ») ; la comparaison ignore la casse, les accents et les
espaces en trop.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def normalize_text(value: Optional[str]) -> str:
    """Minuscules, sans accents, espaces normalisés — pour comparer des
    libellés saisis librement par l'utilisateur (« Façade », « FACADE »)."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


# (code, libellé, groupe, noms par défaut)
ROLES: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    # Architecture : murs et façades
    ("wall_ext", "Mur extérieur", "Murs", ("A-MUR-EXT", "MURS_EXT")),
    ("wall_int", "Mur intérieur", "Murs", ("A-MUR-INT", "MURS_INT")),
    ("wall_hatch", "Hachures de mur", "Murs", ("A-MUR-HACH",)),
    ("facade_outline", "Contour de façade", "Façades", ("A-FAC-CONT",)),
    ("facade_detail", "Détails de façade (dalles, menuiseries)", "Façades", ("A-FAC-DET",)),
    # Ouvertures
    ("opening_window", "Fenêtre", "Ouvertures", ("A-OUV-FEN", "A-FEN", "A-FENETRE")),
    ("opening_door", "Porte", "Ouvertures", ("A-OUV-PRT", "A-PORTE", "A-PTE")),
    ("opening_french_window", "Porte-fenêtre", "Ouvertures", ("A-PORTE-FEN", "A-PFEN")),
    ("opening_bay", "Baie", "Ouvertures", ("A-BAIE",)),
    ("opening_garage_door", "Porte de garage", "Ouvertures", ("A-PORTE-GAR", "A-PGAR")),
    ("opening_generic", "Ouverture (nature déduite de la géométrie)", "Ouvertures",
     ("OUVERTURES", "A-OUV", "A-OUVERTURE", "A-OUVERTURES", "A-MENUISERIE", "MENUISERIES")),
    ("opening_symbol", "Symbole d'ouverture (débattement)", "Ouvertures", ("A-OUV-SYMB",)),
    # Éléments de façade
    ("feature_balcony", "Balcon", "Éléments de façade", ("A-BALCON", "A-BAL")),
    ("feature_terrace", "Terrasse", "Éléments de façade", ("A-TERRASSE", "A-TER")),
    ("feature_railing", "Garde-corps", "Éléments de façade", ("A-GARDE-CORPS", "A-GC")),
    ("feature_cornice", "Corniche", "Éléments de façade", ("A-CORNICHE", "A-CORN")),
    ("feature_roof", "Toiture", "Éléments de façade", ("A-TOITURE", "A-TOIT")),
    ("feature_canopy", "Auvent", "Éléments de façade", ("A-AUVENT", "A-AUV")),
    ("feature_stairs", "Escalier", "Éléments de façade", ("A-ESCALIER", "A-ESC")),
    ("feature_shutter", "Volet", "Éléments de façade", ("A-VOLET",)),
    # Structure
    ("footing_isolated", "Semelle isolée", "Structure", ("S-SEM",)),
    ("footing_strip", "Semelle filante", "Structure", ("S-SEM-FIL",)),
    ("tie_beam", "Longrine", "Structure", ("S-LON",)),
    ("column", "Poteau", "Structure", ("S-POT",)),
    ("beam", "Poutre", "Structure", ("S-POU", "S-POU-CACHE")),
    ("slab", "Dalle", "Structure", ("S-DAL",)),
    ("slab_opening", "Trémie", "Structure", ("S-TREMIE",)),
    ("wall_ref", "Mur de refend (structure)", "Structure", ("S-REF",)),
    # Plans de détail
    ("level", "Niveaux (cotes altimétriques)", "Détails", ("S-NIV",)),
    ("warning", "Hypothèses à vérifier", "Détails", ("X-HYP",)),
)

ROLE_LABELS: Dict[str, str] = {code: label for code, label, _g, _n in ROLES}
DEFAULT_NAMES: Dict[str, Tuple[str, ...]] = {code: names for code, _l, _g, names in ROLES}

# Rôle des lignes qui rattachent un calque à un type d'élément (moteur
# « blocs ») plutôt qu'à un rôle fixe.
ELEMENT_TYPE_ROLE = "element_type"


def _pattern_regex(pattern: str) -> Optional[re.Pattern]:
    """« A-MUR-EXT* » -> ^a\\-mur\\-ext.*$ ; seul « * » est un joker."""
    text = normalize_text(pattern)
    if not text:
        return None
    return re.compile("^" + ".*".join(re.escape(part) for part in text.split("*")) + "$")


def name_matches(pattern: str, layer_name: str) -> bool:
    regex = _pattern_regex(pattern)
    return bool(regex and regex.match(normalize_text(layer_name)))


class LayerConfig:
    """Noms de calque par rôle, et par type d'élément pour le moteur
    « blocs ». `label` dit d'où vient la configuration (« All »,
    « Convention Miro ») pour les messages."""

    def __init__(self, names: Optional[Dict[str, Sequence[str]]] = None,
                 element_types: Optional[Dict[int, Sequence[str]]] = None,
                 label: str = "par défaut"):
        self.names: Dict[str, Tuple[str, ...]] = {
            role: tuple(dict.fromkeys(values)) for role, values in (names or {}).items()}
        self.element_types: Dict[int, Tuple[str, ...]] = {
            type_id: tuple(dict.fromkeys(values)) for type_id, values in (element_types or {}).items()}
        self.label = label

    @classmethod
    def default(cls) -> "LayerConfig":
        return cls(DEFAULT_NAMES, label="par défaut")

    def patterns(self, *roles: str) -> List[str]:
        out: List[str] = []
        for role in roles:
            for name in self.names.get(role, ()):
                if name not in out:
                    out.append(name)
        return out

    def describe(self, *roles: str) -> str:
        """« A-MUR-EXT, MURS_EXT » — pour dire à l'utilisateur où l'on a
        cherché ; signale un rôle sans aucun nom configuré."""
        names = self.patterns(*roles)
        if names:
            return ", ".join(names)
        labels = ", ".join(ROLE_LABELS.get(r, r) for r in roles)
        return f"aucun calque configuré pour « {labels} » (convention {self.label})"

    def resolve(self, layer_names: Iterable[str], *roles: str) -> List[str]:
        """Calques réels du dessin désignés par ces rôles, dans l'ordre des
        noms configurés."""
        return _resolve(layer_names, self.patterns(*roles))

    def element_type_matches(self, type_id: int, layer_name: str) -> bool:
        return any(name_matches(p, layer_name) for p in self.element_types.get(type_id, ()))


def _resolve(layer_names: Iterable[str], patterns: Sequence[str]) -> List[str]:
    layers = list(layer_names)
    found: List[str] = []
    for pattern in patterns:
        regex = _pattern_regex(pattern)
        if not regex:
            continue
        for layer in layers:
            if layer not in found and regex.match(normalize_text(layer)):
                found.append(layer)
    return found
