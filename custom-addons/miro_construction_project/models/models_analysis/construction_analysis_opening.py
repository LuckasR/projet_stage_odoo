import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Codes des types d'élément produits (cf. data/construction_opening_data.xml)
DOOR_TYPE_CODE = 'porte'
WINDOW_TYPE_CODE = 'fenetre'
DOOR_OPENING_TYPES = ('door', 'garage_door')


class ConstructionAnalysisOpening(models.Model):
    """Moteur d'analyse « Ouvertures » : traduit les ouvertures détectées en
    éléments à valider, comme le moteur « Murs » le fait pour les murs.

        détection -> construction.opening -> CE MOTEUR -> brouillons
                                                       -> validation humaine
                                                       -> construction.element
                                                       -> phases

    Une ouverture vue seulement en plan produit quand même un brouillon, sans
    hauteur et avec l'anomalie correspondante : il sera complété quand la
    façade du même niveau sera importée. Importé après ce moteur dans
    __init__.py : son aiguillage doit être le plus extérieur."""
    _inherit = 'construction.analysis'

    engine = fields.Selection(
        selection_add=[('openings', "Ouvertures détectées")],
        ondelete={'openings': 'cascade'})

    def _analyze_plan(self):
        self.ensure_one()
        if self.manual_json or self.engine != 'openings':
            return super()._analyze_plan()

        openings = self._openings_to_review()
        if not openings:
            raise ValidationError(_(
                "Aucune ouverture détectée pour ce plan. Lancez d'abord « Détecter "
                "les ouvertures », ou vérifiez que le plan est classé en vue Plan "
                "ou Façade."))
        return {
            'schema_version': 1,
            'elements': [self._opening_to_item(opening) for opening in openings],
        }

    def _openings_to_review(self):
        """Ouvertures de ce plan, y compris celles qu'il a seulement
        complétées : une façade qui donne la hauteur d'une fenêtre née d'une
        vue en plan doit faire remonter cette fenêtre à la validation."""
        self.ensure_one()
        return self.env['construction.opening'].search([
            '|', ('dwg_file_id', '=', self.file_id.id),
                 ('source_file_ids', 'in', self.file_id.id),
        ])

    @api.model
    def _opening_to_item(self, opening):
        """Une ouverture au format attendu par `_process_result`.

        Dimensions : l = largeur, ep = épaisseur du tableau, h = hauteur,
        allege = hauteur d'allège. Métré : surface de baie (l × h), qui est
        ce que l'on commande et que l'on déduit des surfaces de mur."""
        issues = []
        quantities = {}

        if not opening.width:
            issues.append(_("Largeur inconnue : importez une vue en plan ou en façade"))
        if not opening.thickness:
            issues.append(_(
                "Épaisseur inconnue : importez une vue en plan de ce niveau"))
        if opening.height:
            if opening.width:
                quantities['surface_m2'] = round(opening.area, 3)
        elif opening.wall_position == 'interior':
            # Une porte intérieure n'apparaît sur aucune façade.
            issues.append(_("Hauteur inconnue : une ouverture intérieure n'est "
                            "visible sur aucune façade, à saisir"))
        else:
            issues.append(_("Hauteur inconnue : importez la façade %s de ce niveau")
                          % (opening.orientation or ""))

        dimensions = {}
        if opening.width:
            dimensions['l'] = round(opening.width, 3)
        if opening.thickness:
            dimensions['ep'] = round(opening.thickness, 3)
        if opening.height:
            dimensions['h'] = round(opening.height, 3)
            # L'allège n'a de sens qu'avec la hauteur, relevées ensemble en
            # façade ; une allège nulle (porte) est une vraie mesure.
            dimensions['allege'] = round(opening.sill_height or 0.0, 3)

        confidence = min(max((opening.confidence or 0.0) / 100.0, 0.0), 0.95)
        if issues:
            confidence = max(confidence - 0.15, 0.0)

        has_axis = (opening.start_x, opening.start_y) != (opening.end_x, opening.end_y)
        return {
            'key': self._opening_key(opening),
            'opening_id': opening.id,
            'type': (DOOR_TYPE_CODE if opening.opening_type in DOOR_OPENING_TYPES
                     else WINDOW_TYPE_CODE),
            'level': (opening.level_id.code or opening.level_id.name)
                     if opening.level_id else False,
            'quantities': quantities,
            'dimensions': dimensions,
            'confidence': round(confidence, 2),
            'issue': " ; ".join(issues) or False,
            'source': {
                'page': 1,
                'bbox': [opening.start_x, opening.start_y,
                         opening.end_x, opening.end_y] if has_axis else [],
            },
        }

    @staticmethod
    def _opening_key(opening):
        """Repère stable d'une analyse à l'autre : « OUV-SUD-1.70 ». Le niveau
        est déjà porté par level_id, on ne garde que la désignation."""
        if opening.match_key:
            return "OUV-%s" % opening.match_key.split('|')[-1].upper().replace(
                'OUV-', '', 1)
        return "OUV-%s" % opening.id
