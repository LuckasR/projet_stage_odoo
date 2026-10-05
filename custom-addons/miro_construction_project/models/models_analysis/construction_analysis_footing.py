import base64
import logging
import tempfile
from pathlib import Path

from odoo import _, models
from odoo.exceptions import UserError, ValidationError

from ...service.footing_detection_service import (
    FOOTING_LAYERS,
    FootingDetectionService,
)
from ...service.plan_analysis import PlanContext

_logger = logging.getLogger(__name__)

# $INSUNITS -> mètres, comme le moteur « blocs » (construction_analysis_dxf)
UNIT_TO_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 14: 0.1}


class ConstructionAnalysisFooting(models.Model):
    """Moteur d'analyse « Fondations » : lit la géométrie des calques de
    fondation au lieu des blocs DXF.

    Il s'insère au même endroit que le moteur « blocs » (`_analyze_plan`) et
    ne prend la main que sur les analyses dont le moteur est « footings » ;
    sinon il laisse la place au moteur historique. Ce module doit donc être
    importé APRÈS construction_analysis_dxf (cf. __init__.py), pour que son
    aiguillage soit le plus extérieur.

    Toute la détection est dans service/footing_detection_service.py : ici on
    ne fait que fournir le fichier, le contexte du plan et l'échelle."""
    _inherit = 'construction.analysis'

    def _analyze_plan(self):
        self.ensure_one()
        if self.manual_json or self.engine != 'footings':
            return super()._analyze_plan()

        dwg = self.file_id
        if not dwg.dxf_file:
            raise UserError(_(
                "Aucun fichier DXF disponible pour ce plan. Traitez-le d'abord "
                "(bouton « Traiter / Convertir »)."))

        service = self._footing_service(dwg)
        footings = service.detect_footings()

        if not footings:
            raise ValidationError(_(
                "Aucun ouvrage de fondation détecté sur ce plan. Vérifiez que "
                "les semelles et longrines sont bien dessinées sur les calques "
                "%s, et que le plan est classé en vue « Plan ».")
                % ", ".join(FOOTING_LAYERS))

        return service.to_analysis_result(footings)

    def _footing_service(self, dwg):
        """Instancie le service sur une copie temporaire du DXF, avec le
        classement du plan et l'échelle relevée à l'import."""
        self.ensure_one()
        level = dwg.level_ids[:1]
        view = dwg.view_ids[:1]
        context = PlanContext.build(
            view=view.code or view.name,
            level=level.code or level.name,
            level_label=level.name,
            plan_types=[t.code or t.name for t in dwg.plan_type_ids],
            title=dwg.filename,
        )

        meta = dwg.metadata_id[:1]
        unit_scale = UNIT_TO_M.get(meta.units_code, 1.0) if meta else 1.0

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(base64.b64decode(dwg.dxf_file))
            tmp_path = tmp.name
        try:
            return FootingDetectionService(
                tmp_path, context=context, unit_scale=unit_scale)
        finally:
            # ezdxf a déjà chargé le document en mémoire : le fichier
            # temporaire n'a plus lieu d'être.
            Path(tmp_path).unlink(missing_ok=True)
