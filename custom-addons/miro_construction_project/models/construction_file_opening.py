"""Détection des ouvertures sur un plan DWG/DXF : enfilage, exécution et
consolidation.

Le calcul est dans service/opening_detection_service.py ; ici on fournit le
fichier et le contexte, on résout les niveaux et on consolide le résultat
dans construction.opening — exactement comme les murs :

    import d'un plan  -> détection (job) -> construction.opening complétées
                      -> analyse « ouvertures » -> brouillons à valider
                      -> éléments de construction -> phases

Une vue en plan et une vue en façade du même niveau se complètent : la
première donne largeur et épaisseur, la seconde hauteur et allège.
"""

import base64
import logging
import tempfile
from pathlib import Path

from odoo import Command, _, fields, models
from odoo.exceptions import UserError

from ..service.opening_detection_service import (
    SUPPORTED_VIEWS,
    OpeningDetectionService,
    merge_detected_openings,
)

_logger = logging.getLogger(__name__)

# Canal dédié : capacité définie dans data/queue_job_data.xml.
OPENING_DETECTION_CHANNEL = "root.construction_opening_detection"

# $INSUNITS -> mètres, comme les autres moteurs.
UNIT_TO_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 14: 0.1}

# Analyses dont le lancement entraîne celui des ouvertures : les portes et
# fenêtres se lisent sur les mêmes plans que les murs et les façades.
OPENING_COMPANION_ANALYSES = ("walls", "facade")


class ConstructionDwgFileOpening(models.Model):
    _inherit = "construction.dwg.files"

    opening_ids = fields.One2many(
        "construction.opening", "dwg_file_id", string="Ouvertures détectées")
    opening_count = fields.Integer(compute="_compute_opening_count")

    opening_detection_state = fields.Selection([
        ("draft", "Non lancée"),
        ("queued", "En file d'attente"),
        ("in_progress", "En cours"),
        ("done", "Terminée"),
        ("failed", "Échec"),
    ], string="État détection des ouvertures", default="draft", copy=False)
    opening_detection_job_id = fields.Many2one(
        "queue.job", string="Job de détection des ouvertures",
        copy=False, readonly=True)
    opening_detection_error = fields.Text(
        "Erreur détection des ouvertures", copy=False, readonly=True)

    def _compute_opening_count(self):
        for rec in self:
            rec.opening_count = self.env["construction.opening"].search_count([
                "|", ("dwg_file_id", "=", rec.id),
                     ("source_file_ids", "in", rec.id)])

    # ------------------------------------------------------------------
    # AIGUILLAGE
    # ------------------------------------------------------------------
    def _auto_enqueue_analyses(self, strict=False):
        """Les ouvertures accompagnent les murs et les façades : elles se
        lisent sur les mêmes plans (architecture, en vue plan ou façade).
        Aucun type de plan n'a donc à les déclarer séparément."""
        launched = super()._auto_enqueue_analyses(strict=strict)
        if (set(launched) & set(OPENING_COMPANION_ANALYSES)
                and self._enqueue_analysis_openings()):
            launched.append("openings")
        return launched

    def _opening_detection_supported(self):
        self.ensure_one()
        return self._wall_detection_context().view in SUPPORTED_VIEWS

    def _enqueue_analysis_openings(self):
        """Une vue qui ne montre pas d'ouverture (coupe, détail, schéma) n'est
        pas enfilée, plutôt que de lancer un calcul qui ne trouvera rien."""
        self.ensure_one()
        if not self._opening_detection_supported():
            _logger.info(
                "Vue « %s » non exploitable pour les ouvertures : %s ignoré",
                self.view_ids[:1].name or "?", self.filename)
            return False
        return self._enqueue_opening_detection(
            description=_("Détection des ouvertures (auto) — %s") % self.filename)

    # ------------------------------------------------------------------
    # CALCUL
    # ------------------------------------------------------------------
    def _unit_scale(self):
        self.ensure_one()
        meta = self.metadata_id[:1]
        return UNIT_TO_M.get(meta.units_code, 1.0) if meta else 1.0

    def _detect_openings_from_dxf(self):
        """Lit le DXF et consolide les ouvertures. Ne sait rien de
        l'asynchronisme : c'est `_detect_openings_job` qui l'entoure."""
        self.ensure_one()
        if not self.dxf_file:
            raise UserError(_(
                "Aucun fichier DXF disponible pour la détection des ouvertures. "
                "Traitez d'abord le fichier (bouton « Traiter / Convertir »)."))

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(base64.b64decode(self.dxf_file))
            tmp_path = tmp.name
        try:
            service = OpeningDetectionService(
                tmp_path, context=self._wall_detection_context(),
                unit_scale=self._unit_scale())
            detected = service.detect_openings()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return self._apply_detected_openings(detected)

    # ------------------------------------------------------------------
    # ÉCRITURE : compléter les ouvertures déjà connues
    # ------------------------------------------------------------------
    _OPENING_MERGE_FIELDS = [
        "name", "match_key", "opening_type", "wall_position", "orientation",
        "facade_offset", "mark", "layer", "start_x", "start_y", "end_x",
        "end_y", "center_x", "center_y", "width", "thickness", "height",
        "sill_height", "lintel_height", "confidence", "detection_method",
    ]

    def _apply_detected_openings(self, detected_openings):
        """Ce que cette vue observe complète les ouvertures du niveau, sans
        jamais écraser ce qu'une autre vue avait renseigné.

        Une façade montre plusieurs étages : le niveau est résolu ouverture
        par ouverture, par la même règle que les murs (`_resolve_wall_levels`
        : rang d'étage -> niveau du fichier trié par élévation), et la
        consolidation se fait niveau par niveau."""
        self.ensure_one()
        Opening = self.env["construction.opening"]
        view = self.view_ids[:1]

        # Relance : on repart de zéro pour les ouvertures que ce plan est
        # seul à connaître ; celles qu'un autre plan a complétées restent.
        own = Opening.search([("dwg_file_id", "=", self.id)])
        own.filtered(lambda o: not (o.source_file_ids - self)).unlink()

        traceability = {"source_file_ids": [Command.link(self.id)]}
        if view:
            traceability["source_view_ids"] = [Command.link(view.id)]

        touched = Opening
        created = Opening
        updated = 0
        for level, openings in self._resolve_wall_levels(detected_openings).items():
            existing = Opening.search([
                ("project_id", "=", self.project_id.id),
                ("level_id", "=", level.id if level else False),
            ])
            plan = merge_detected_openings(
                existing.read(self._OPENING_MERGE_FIELDS), openings)

            for opening_id, vals in plan.updates:
                record = Opening.browse(opening_id)
                record.write({**vals, **traceability})
                touched |= record
            updated += len(plan.updates)

            created |= Opening.create([
                dict(vals, dwg_file_id=self.id, level_id=level.id or False,
                     **traceability)
                for vals in plan.creates
            ])

        Opening._link_host_walls(self.project_id)
        Opening._link_elements(created | touched)

        _logger.info("%s (vue %s) : %d ouverture(s) créée(s), %d complétée(s)",
                     self.filename, view.name or "plan", len(created), updated)
        return created | touched

    def _apply_detected_walls(self, detected_walls):
        """Des murs fraîchement détectés peuvent porter des ouvertures déjà
        connues : rattachement et épaisseur sont recalculés. Les ouvertures
        ainsi complétées repassent par la validation."""
        walls = super()._apply_detected_walls(detected_walls)
        completed = self.env["construction.opening"]._link_host_walls(self.project_id)
        for dwg in completed.dwg_file_id:
            dwg._enqueue_analysis_opening_elements()
        return walls

    def _enqueue_analysis_opening_elements(self):
        """Fait remonter les ouvertures dans le circuit de validation :
        analyse -> brouillons -> éléments -> phases. Sans ouverture à
        valider, aucune analyse n'est créée (elle échouerait aussitôt)."""
        self.ensure_one()
        if self.analysis_ids.filtered(
                lambda a: a.state == "running" and a.engine == "openings"):
            return False
        if not self.env["construction.opening"].search_count([
                "|", ("dwg_file_id", "=", self.id),
                     ("source_file_ids", "in", self.id)]):
            _logger.info("Aucune ouverture sur %s : pas d'analyse d'éléments",
                         self.filename)
            return False

        analysis = self.env["construction.analysis"].create({
            "file_id": self.id,
            "revision": self.filename,
            "engine": "openings",
        })
        analysis.action_start()
        return analysis

    # ------------------------------------------------------------------
    # ASYNCHRONE
    # ------------------------------------------------------------------
    def _enqueue_opening_detection(self, description=None):
        self.ensure_one()
        if not self.dxf_file:
            raise UserError(_("Aucun fichier DXF disponible pour la détection des ouvertures."))
        if self.opening_detection_state in ("queued", "in_progress"):
            _logger.info("Détection d'ouvertures déjà en cours pour %s", self.filename)
            return False

        self.opening_detection_state = "queued"
        self.opening_detection_error = False
        job = self.with_delay(
            channel=OPENING_DETECTION_CHANNEL,
            description=description or _("Détection des ouvertures — %s") % self.filename,
            max_retries=2,
        )._detect_openings_job()
        self.opening_detection_job_id = job.db_record().id
        return True

    def _detect_openings_job(self):
        """Corps exécuté par le worker queue_job, dans sa propre transaction."""
        self.ensure_one()
        self.opening_detection_state = "in_progress"
        # Commit immédiat : l'utilisateur voit « En cours » pendant le calcul.
        self.env.cr.commit()

        try:
            self._detect_openings_from_dxf()
            self.opening_detection_state = "done"
            self.opening_detection_error = False
            # Les ouvertures rejoignent le circuit commun de validation.
            self._enqueue_analysis_opening_elements()
        except Exception as exc:
            _logger.exception("Échec de la détection d'ouvertures pour %s", self.filename)
            self.opening_detection_state = "failed"
            self.opening_detection_error = str(exc)
            raise
        return True

    def _opening_detection_related_action(self):
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
    def action_detect_openings(self):
        self.ensure_one()
        if not self._opening_detection_supported():
            raise UserError(_(
                "La vue « %s » ne montre pas les ouvertures : classez ce plan en "
                "vue « Plan » ou « Façade ».")
                % (self.view_ids[:1].name or self._wall_detection_context().view))
        self._enqueue_opening_detection()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Détection des ouvertures lancée"),
                "message": _("Le traitement se fait en arrière-plan. "
                             "Rafraîchissez la fiche pour suivre l'avancement."),
                "sticky": False,
                "type": "info",
            },
        }

    def _viewer_menu_items(self):
        items = super()._viewer_menu_items()
        items.append({"key": "openings", "label": _("Ouvertures (portes, fenêtres)"),
                      "icon": "fa-columns", "method": "action_view_openings_visual",
                      "sequence": 40})
        return items

    def action_view_openings_visual(self):
        """Plan et élévations des ouvertures de ce fichier, y compris celles
        qu'il a seulement complétées."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/construction/openings/{self.id}",
            "target": "new",
        }

    def action_view_openings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Ouvertures"),
            "res_model": "construction.opening",
            "view_mode": "tree,form",
            "domain": ["|", ("dwg_file_id", "=", self.id),
                       ("source_file_ids", "in", self.id)],
            "context": {"default_dwg_file_id": self.id},
        }
