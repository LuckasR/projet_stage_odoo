import logging

from odoo import _, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Code du type d'élément représentant un mur (cf. données du module)
WALL_TYPE_CODE = 'mur'


class ConstructionAnalysisWall(models.Model):
    """Moteur d'analyse « Murs » : traduit les murs déjà détectés en éléments
    à valider.

    La détection géométrique elle-même reste dans wall_detection_service et
    écrit dans construction.wall — c'est là que vivent la géométrie, le
    visualiseur et la complétion d'une vue à l'autre. Ce moteur ne fait que
    présenter le résultat dans le circuit commun :

        détection -> construction.wall -> CE MOTEUR -> brouillons
                                                    -> validation humaine
                                                    -> construction.element
                                                    -> phases

    Un mur dont la hauteur n'est pas encore connue produit quand même un
    brouillon, sans métré et avec l'anomalie correspondante : il sera complété
    quand une façade ou une coupe du même niveau sera importée."""
    _inherit = 'construction.analysis'

    def _analyze_plan(self):
        self.ensure_one()
        if self.manual_json or self.engine != 'walls':
            return super()._analyze_plan()

        walls = self._walls_to_review()
        if not walls:
            raise ValidationError(_(
                "Aucun mur détecté pour ce plan. Lancez d'abord « Détecter les "
                "murs », ou vérifiez que le plan est bien classé en vue Plan, "
                "Façade ou Coupe."))

        return {
            'schema_version': 1,
            'elements': [self._wall_to_item(wall) for wall in walls],
        }

    def _walls_to_review(self):
        """Murs de ce plan, y compris ceux qu'il a seulement complétés : une
        vue en façade qui renseigne la hauteur d'un mur né d'une vue en plan
        doit faire remonter ce mur à la validation."""
        self.ensure_one()
        return self.env['construction.wall'].search([
            '|', ('dwg_file_id', '=', self.file_id.id),
                 ('source_file_ids', 'in', self.file_id.id),
        ])

    def _wall_to_item(self, wall):
        """Un mur au format attendu par `_process_result`.

        La clé vient de `match_key`, l'identité du mur dans son niveau : c'est
        elle qui garantit qu'une seconde analyse (après import d'une façade)
        retombe sur le même brouillon et le même élément, au lieu d'en créer
        un second."""
        issues = []
        quantities = {}

        if wall.height:
            # Surface NETTE : les ouvertures percées dans le mur sont déduites.
            quantities['surface_m2'] = round(wall.net_area, 3)
            quantities['beton_m3'] = round(wall.net_volume, 3)
            if wall.openings_without_height:
                issues.append(_(
                    "%d ouverture(s) sans hauteur : leur surface n'est pas "
                    "encore déduite du mur") % wall.openings_without_height)
        else:
            issues.append(_(
                "Hauteur inconnue : importez une vue en façade ou en coupe de "
                "ce niveau pour obtenir les métrés"))

        if not wall.thickness:
            issues.append(_("Épaisseur inconnue : importez une vue en plan"))

        dimensions = {'l': round(wall.length, 3)}
        if wall.thickness:
            dimensions['ep'] = round(wall.thickness, 3)
        if wall.height:
            dimensions['h'] = round(wall.height, 3)
        if wall.opening_area:
            dimensions['ouvertures_m2'] = round(wall.opening_area, 3)

        # La confiance des murs est notée sur 100, celle des brouillons sur 1.
        confidence = min(max((wall.confidence or 0.0) / 100.0, 0.0), 0.95)
        if issues:
            confidence = max(confidence - 0.15, 0.0)

        return {
            'key': self._wall_key(wall),
            'wall_id': wall.id,
            'type': WALL_TYPE_CODE,
            'level': (wall.level_id.code or wall.level_id.name) if wall.level_id else False,
            'quantities': quantities,
            'dimensions': dimensions,
            'confidence': round(confidence, 2),
            'issue': " ; ".join(issues) or False,
            'source': {
                'page': 1,
                'bbox': [wall.start_x, wall.start_y, wall.end_x, wall.end_y],
            },
        }

    @staticmethod
    def _wall_key(wall):
        """Repère lisible et stable d'une analyse à l'autre. `match_key` vaut
        « r+0|facade-nord » ou « r+0|axe-6.00--12.00 » : le niveau est déjà
        porté par level_id, on ne garde donc que la désignation."""
        if wall.match_key:
            return "MUR-%s" % wall.match_key.split('|')[-1].upper()
        # Murs détectés avant l'introduction des clés d'identité
        return "MUR-%s" % wall.id
