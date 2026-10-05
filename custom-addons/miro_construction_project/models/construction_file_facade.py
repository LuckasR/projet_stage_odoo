"""Détection de façade sur un plan DWG/DXF : enfilage, exécution et écriture.

Le calcul est dans service/facade_detection_service.py ; ici on ne fait que
fournir le fichier et le contexte, résoudre les niveaux du projet et écrire
le résultat dans construction.facade et ses enfants.

Comme pour les murs, le calcul tourne dans un job queue_job : lire un DXF de
plusieurs mégaoctets prend des dizaines de secondes et ne doit pas retenir le
curseur de la requête HTTP qui l'a déclenché.
"""

import base64
import logging
import tempfile
from pathlib import Path

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from ..service.facade_detection_service import FacadeDetectionService
from ..service.plan_analysis import VIEW_ELEVATION

_logger = logging.getLogger(__name__)

# Canal dédié : capacité définie dans data/queue_job_data.xml.
FACADE_DETECTION_CHANNEL = "root.construction_facade_detection"

# $INSUNITS -> mètres, comme les moteurs « blocs » et « fondations ».
UNIT_TO_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 14: 0.1}


class ConstructionDwgFileFacade(models.Model):
    _inherit = "construction.dwg.files"

    facade_ids = fields.One2many(
        "construction.facade", "dwg_file_id", string="Façades relevées")
    facade_count = fields.Integer(compute="_compute_facade_count")

    facade_detection_state = fields.Selection([
        ("draft", "Non lancée"),
        ("queued", "En file d'attente"),
        ("in_progress", "En cours"),
        ("done", "Terminée"),
        ("failed", "Échec"),
    ], string="État détection des façades", default="draft", copy=False)
    facade_detection_job_id = fields.Many2one(
        "queue.job", string="Job de détection des façades",
        copy=False, readonly=True)
    facade_detection_error = fields.Text(
        "Erreur détection des façades", copy=False, readonly=True)

    @api.depends("facade_ids")
    def _compute_facade_count(self):
        for rec in self:
            rec.facade_count = len(rec.facade_ids)

    # ------------------------------------------------------------------
    # AIGUILLAGE PAR TYPE DE PLAN
    # ------------------------------------------------------------------
    def _auto_enqueue_analyses(self, strict=False):
        """La détection de façade se déclenche sur la VUE, pas sur le type de
        plan : un plan architectural classé en vue « Façade » doit la lancer,
        quel que soit l'analyseur configuré sur son type. Les autres analyses
        restent pilotées par les types de plan."""
        launched = super()._auto_enqueue_analyses(strict=strict)
        if "facade" not in launched and self._enqueue_analysis_facade():
            launched.append("facade")
        return launched

    def _enqueue_analysis_facade(self):
        """Analyse « Façade », appelée par `_auto_enqueue_analyses`.

        Une vue qui n'est pas une élévation ne montre pas de façade : on ne
        l'enfile pas plutôt que de lancer un calcul qui ne trouvera rien."""
        self.ensure_one()
        context = self._wall_detection_context()
        if context.view != VIEW_ELEVATION:
            _logger.info(
                "Vue « %s » : pas une façade, détection ignorée pour %s",
                self.view_ids[:1].name or context.view, self.filename)
            return False
        return self._enqueue_facade_detection(
            description=_("Détection des façades (auto) — %s") % self.filename)

    # ------------------------------------------------------------------
    # HAUTEUR D'ÉTAGE REPRISE D'UNE FAÇADE DÉJÀ VALIDÉE
    # ------------------------------------------------------------------
    def _apply_detected_walls(self, detected_walls):
        """Un mur qu'aucune vue de ce plan n'a pu mesurer en hauteur hérite de
        la hauteur d'étage d'une façade déjà VALIDÉE pour son niveau (n'importe
        quelle orientation, extérieur ou intérieur).

        Sans façade validée pour ce niveau, `_fill_wall_heights` ne trouve
        rien et ne fait rien : ce mur reste sans hauteur jusqu'à validation.
        Utile quand ce plan (vue en plan, coupe) est importé APRÈS qu'une
        façade a déjà été validée."""
        walls = super()._apply_detected_walls(detected_walls)
        self.env["construction.facade"]._fill_wall_heights(self.project_id)
        return walls

    # ------------------------------------------------------------------
    # CALCUL
    # ------------------------------------------------------------------
    def _detect_facades_from_dxf(self):
        """Lit le DXF et écrit les façades. Ne sait rien de l'asynchronisme :
        c'est `_detect_facades_job` qui l'entoure de la gestion d'état."""
        self.ensure_one()
        if not self.dxf_file:
            raise UserError(_(
                "Aucun fichier DXF disponible pour la détection des façades. "
                "Traitez d'abord le fichier (bouton « Traiter / Convertir »)."))

        meta = self.metadata_id[:1]
        unit_scale = UNIT_TO_M.get(meta.units_code, 1.0) if meta else 1.0

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(base64.b64decode(self.dxf_file))
            tmp_path = tmp.name
        try:
            service = FacadeDetectionService(
                tmp_path, context=self._wall_detection_context(),
                unit_scale=unit_scale)
            detected = service.detect_facades()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return self._apply_detected_facades(detected)

    # ------------------------------------------------------------------
    # ÉCRITURE
    # ------------------------------------------------------------------
    def _apply_detected_facades(self, detected_facades):
        """Écrit les façades détectées, en repartant de zéro pour leur contenu.

        Une façade déjà validée n'est jamais réécrite : c'est le seul moyen de
        réimporter un plan corrigé sans perdre les corrections saisies à la
        main sur les façades déjà relues."""
        self.ensure_one()
        Facade = self.env["construction.facade"]
        written = Facade

        for detected in detected_facades:
            levels = self._resolve_facade_levels(detected)
            existing = Facade.search([
                ("project_id", "=", self.project_id.id),
                ("match_key", "=", detected.match_key),
            ], limit=1)

            if existing.is_validated:
                _logger.info(
                    "Façade « %s » déjà validée : détection ignorée pour %s",
                    existing.name, self.filename)
                continue

            # Les niveaux d'abord : les ouvertures et les ouvrages s'y
            # rattachent, il faut donc qu'ils existent avant d'être écrits.
            vals = detected.to_odoo_vals()
            vals["source_file_ids"] = [Command.link(self.id)]
            vals["level_ids"] = self._facade_level_vals(detected, levels)

            if existing:
                existing.write(vals)
                facade = existing
            else:
                facade = Facade.create(dict(vals, dwg_file_id=self.id))

            facade.write(self._facade_content_vals(detected, facade))
            self._link_facade_walls(facade, levels)
            written |= facade

        _logger.info("%s : %d façade(s) écrite(s)", self.filename, len(written))
        return written

    def _resolve_facade_levels(self, detected):
        """Niveau du projet correspondant à chaque bande d'étage.

        Le service ne connaît que le rang de la bande (0 = la plus basse) : on
        le résout contre `level_ids`, trié par élévation croissante. Le fichier
        doit donc porter TOUS les niveaux que le plan montre, pas seulement
        le plus bas."""
        self.ensure_one()
        ordered = self.level_ids.sorted(key=lambda level: level.elevation)
        resolved = {}
        for band in detected.levels:
            if band.floor_index < len(ordered):
                resolved[band.floor_index] = ordered[band.floor_index]
            else:
                resolved[band.floor_index] = self.env["construction.plan.level"]
                _logger.warning(
                    "%s : étage %d détecté sur la façade « %s » sans niveau "
                    "correspondant sélectionné sur le fichier (%d niveau(x)) — "
                    "ajoutez le niveau manquant.",
                    self.filename, band.floor_index, detected.name, len(ordered))
        return resolved

    def _facade_level_vals(self, detected, levels):
        """Bandes d'étage. On remplace tout : les enfants décrivent ce que CE
        plan montre, une relance doit refléter le dessin corrigé plutôt que
        cumuler l'ancien et le nouveau."""
        self.ensure_one()
        commands = [Command.clear()]
        for band in detected.levels:
            level = levels.get(band.floor_index)
            vals = band.to_odoo_vals()
            vals["level_id"] = level.id if level else False
            vals["name"] = level.name if level else _("Étage %s") % band.floor_index
            commands.append(Command.create(vals))
        return commands

    @staticmethod
    def _facade_content_vals(detected, facade):
        """Ouvertures, ouvrages, cotes et annotations, rattachés à la bande
        d'étage que le service leur a assignée."""
        bands = {band.floor_index: band.id for band in facade.level_ids}

        def with_band(item):
            vals = item.to_odoo_vals()
            vals["facade_level_id"] = bands.get(item.floor_index, False)
            return Command.create(vals)

        return {
            "opening_ids": [Command.clear()] + [with_band(o) for o in detected.openings],
            "feature_ids": [Command.clear()] + [with_band(f) for f in detected.features],
            "dimension_ids": [Command.clear()] + [
                Command.create(d.to_odoo_vals()) for d in detected.dimensions],
            "annotation_ids": [Command.clear()] + [
                Command.create(a.to_odoo_vals()) for a in detected.annotations],
        }

    def _link_facade_walls(self, facade, levels):
        """Rattache les murs extérieurs de même orientation et de même niveau.

        Les murs restent dans construction.wall, où ils se complètent d'une vue
        à l'autre : la façade ne fait que les regrouper. Sans orientation, le
        rapprochement n'est pas fiable — on s'abstient plutôt que de rattacher
        le premier mur venu."""
        self.ensure_one()
        if not facade.orientation:
            return

        level_ids = [level.id for level in levels.values() if level]
        domain = [
            ("project_id", "=", self.project_id.id),
            ("orientation", "=", facade.orientation),
            "|", ("facade_id", "=", False), ("facade_id", "=", facade.id),
        ]
        if level_ids:
            domain.append(("level_id", "in", level_ids))
        self.env["construction.wall"].search(domain).facade_id = facade.id

    # ------------------------------------------------------------------
    # ASYNCHRONE
    # ------------------------------------------------------------------
    def _enqueue_facade_detection(self, description=None):
        self.ensure_one()
        if not self.dxf_file:
            raise UserError(_(
                "Aucun fichier DXF disponible pour la détection des façades."))

        if self.facade_detection_state in ("queued", "in_progress"):
            _logger.info("Détection de façades déjà en cours pour %s", self.filename)
            return False

        self.facade_detection_state = "queued"
        self.facade_detection_error = False

        job = self.with_delay(
            channel=FACADE_DETECTION_CHANNEL,
            description=description or _("Détection des façades — %s") % self.filename,
            max_retries=2,
        )._detect_facades_job()
        self.facade_detection_job_id = job.db_record().id
        return True

    def _detect_facades_job(self):
        """Corps exécuté par le worker queue_job, dans sa propre transaction."""
        self.ensure_one()
        self.facade_detection_state = "in_progress"
        # Commit immédiat pour que l'utilisateur voie « En cours » pendant le
        # calcul, plutôt que l'état « En file d'attente ».
        self.env.cr.commit()

        try:
            self._detect_facades_from_dxf()
            self.facade_detection_state = "done"
            self.facade_detection_error = False
        except Exception as exc:
            _logger.exception("Échec de la détection de façades pour %s", self.filename)
            self.facade_detection_state = "failed"
            self.facade_detection_error = str(exc)
            raise

        return True

    def _facade_detection_related_action(self):
        """Related action du job : clic sur le job -> ouvre ce plan."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    # ------------------------------------------------------------------
    # BOUTONS
    # ------------------------------------------------------------------
    def action_detect_facades(self):
        self.ensure_one()
        context = self._wall_detection_context()
        if context.view != VIEW_ELEVATION:
            raise UserError(_(
                "La vue « %s » ne montre pas de façade : classez ce plan en "
                "vue « Façade » pour lancer cette analyse.")
                % (self.view_ids[:1].name or context.view))

        self._enqueue_facade_detection()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Détection des façades lancée"),
                "message": _("Le traitement se fait en arrière-plan. "
                             "Rafraîchissez la fiche pour suivre l'avancement."),
                "sticky": False,
                "type": "info",
            },
        }

    def action_view_facades(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Façades relevées"),
            "res_model": "construction.facade",
            "view_mode": "tree,form",
            "domain": [("dwg_file_id", "=", self.id)],
            "context": {"default_dwg_file_id": self.id},
        }
