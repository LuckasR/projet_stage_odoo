import json
import logging
import re

from odoo import _, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Tags d'attributs de bloc reconnus (insensibles à la casse)
KEY_TAGS = ('NUM', 'NUMERO', 'REPERE', 'MARK', 'REF', 'NOM', 'NAME', 'ID')
LEVEL_TAGS = ('NIVEAU', 'NIV', 'ETAGE', 'LEVEL')
DIM_TAGS = {
    'l': ('L', 'LONGUEUR', 'LENGTH'),
    'w': ('B', 'LARGEUR', 'W', 'WIDTH'),
    'h': ('H', 'HAUTEUR', 'EP', 'EPAISSEUR', 'HEIGHT'),
}
QTY_TAGS = {
    'beton_m3': ('BETON_M3', 'BETON', 'VOLUME'),
    'acier_kg': ('ACIER_KG', 'ACIER'),
    'coffrage_m2': ('COFFRAGE_M2', 'COFFRAGE'),
}
# $INSUNITS -> mètres (pour la clé de secours basée sur la position)
UNIT_TO_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 14: 0.1}


def _to_float(value):
    """« 1,20 » / « 1.2 m » -> 1.2 ; None si illisible."""
    if value is None:
        return None
    match = re.search(r'-?\d+(?:[.,]\d+)?', str(value))
    return float(match.group().replace(',', '.')) if match else None


def _first(attrs, tags):
    for tag in tags:
        if tag in attrs and str(attrs[tag]).strip():
            return attrs[tag]
    return None


class ConstructionAnalysisDxf(models.Model):
    """Analyse « Éléments » V1 : lit les blocs (INSERT) déjà extraits dans
    construction.dwg.block, sans reparser le DXF.

    Sélection des types d'éléments : selon les TYPES DE PLAN du fichier
    (ex. Semelle -> plans FOND/COFF), voir construction.dwg.files._eligible_element_types().
    Niveau : attribut NIVEAU du bloc s'il correspond à un niveau du plan ; sinon le niveau
    unique du plan ; sinon non déterminé (anomalie signalée).

    Conventions sur les attributs de bloc (valeurs de dimensions en MÈTRES) :
      - repère  : NUM / REPERE / MARK …            -> clé de l'élément (S1)
      - niveau  : NIVEAU / ETAGE …                 -> niveau de l'élément
      - dimensions : L, B (ou LARGEUR), H (ou EP)   -> béton = L×B×H, coffrage = 2(L+B)×H
      - quantités explicites : BETON_M3, ACIER_KG, COFFRAGE_M2 (prioritaires)
    """
    _inherit = 'construction.analysis'

    def _analyze_plan(self):
        self.ensure_one()
        if self.manual_json:
            return super()._analyze_plan()

        dwg = self.file_id
        types = dwg._eligible_element_types()
        if not types:
            raise ValidationError(_(
                "Aucun type d'élément applicable à ce plan (types de plan : %s). "
                "Vérifiez les mots-clés DXF et les « types de plan concernés » "
                "dans Construction > Configuration > Types d'éléments.")
                % (', '.join(dwg.plan_type_ids.mapped('code')) or _("aucun")))

        meta = dwg.metadata_id[:1]
        to_m = UNIT_TO_M.get(meta.units_code, 1.0) if meta else 1.0
        levels = dwg.level_ids

        items = []
        for block in dwg.block_ids:
            etype = self._match_type(types, block.block_name, block.layer)
            if not etype:
                continue
            items.append(self._block_to_item(block, etype, to_m, levels))

        if not items:
            raise ValidationError(_(
                "Aucun bloc du plan ne correspond aux types d'éléments applicables "
                "(%s blocs examinés, types testés : %s).")
                % (len(dwg.block_ids), ', '.join(types.mapped('code'))))
        return {'schema_version': 1, 'elements': items}

    @staticmethod
    def _match_type(types, block_name, layer):
        bname, lname = (block_name or '').lower(), (layer or '').lower()
        for etype in types:
            kb = (etype.dxf_block_keyword or '').lower()
            kl = (etype.dxf_layer_keyword or '').lower()
            if (kb and kb in bname) or (kl and kl in lname):
                return etype
        return None

    @staticmethod
    def _resolve_level(attrs, levels):
        """Retourne (niveau ou None, anomalie ou None)."""
        raw = _first(attrs, LEVEL_TAGS)
        if raw:
            wanted = str(raw).strip().lower()
            for lvl in levels:
                if wanted in ((lvl.code or '').strip().lower(), (lvl.name or '').strip().lower()):
                    return lvl, None
            return None, _("Niveau « %s » absent des niveaux du plan") % raw
        if len(levels) == 1:
            return levels[0], None
        if len(levels) > 1:
            return None, _("Niveau non déterminé (plan multi-niveaux : ajoutez un attribut NIVEAU)")
        return None, None

    @classmethod
    def _block_to_item(cls, block, etype, to_m, levels):
        try:
            raw = json.loads(block.attributes) if block.attributes else {}
        except ValueError:
            raw = {}
        attrs = {str(k).strip().upper(): v for k, v in raw.items()}
        issues = []

        # --- niveau ---
        level, level_issue = cls._resolve_level(attrs, levels)
        if level_issue:
            issues.append(level_issue)

        # --- clé ---
        key_raw = _first(attrs, KEY_TAGS)
        has_key = bool(key_raw)
        if has_key:
            key = str(key_raw).strip()
        else:
            prefix = (etype.code or 'EL').upper()
            key = "%s_x%d_y%d" % (
                prefix, round(block.pos_x * to_m * 100), round(block.pos_y * to_m * 100))
            issues.append(_("Clé générée depuis la position (aucun attribut repère)"))

        # --- dimensions & quantités ---
        dims = {k: _to_float(_first(attrs, tags)) for k, tags in DIM_TAGS.items()}
        dims = {k: v for k, v in dims.items() if v is not None}
        qty = {k: _to_float(_first(attrs, tags)) for k, tags in QTY_TAGS.items()}
        qty = {k: v for k, v in qty.items() if v is not None}

        if all(k in dims for k in ('l', 'w', 'h')):
            l, w, h = dims['l'], dims['w'], dims['h']
            qty.setdefault('beton_m3', round(l * w * h, 3))
            qty.setdefault('coffrage_m2', round(2 * (l + w) * h, 3))
        if 'acier_kg' not in qty and qty.get('beton_m3') and etype.steel_ratio_kg_m3:
            qty['acier_kg'] = round(qty['beton_m3'] * etype.steel_ratio_kg_m3, 1)
        if not qty:
            issues.append(_("Aucune dimension ni quantité lisible dans les attributs"))

        confidence = 0.4 + (0.3 if has_key else 0.0) + (0.25 if qty else 0.0)
        if level_issue:
            confidence -= 0.1
        return {
            'key': key,
            'type': etype.code,
            'level': (level.code or level.name) if level else False,
            'quantities': qty,
            'dimensions': dims,
            'confidence': round(min(max(confidence, 0.0), 0.95), 2),
            'issue': " ; ".join(issues) or False,
            'source': {
                'page': 1,
                'bbox': [block.pos_x, block.pos_y, block.pos_x, block.pos_y],
                'handle': block.handle,
            },
        }
