import base64
import subprocess
import tempfile
import logging
from pathlib import Path

from psycopg2 import OperationalError

from odoo import api, models, fields, Command
from odoo.exceptions import UserError, ValidationError
from odoo.service.model import PG_CONCURRENCY_ERRORS_TO_RETRY
from odoo.tools import config
from ...service.wall_detection_service import (
    PlanContext,
    WallDetectionService,
    merge_detected_walls,
)
from ...service.plan_analysis import normalize_text

_logger = logging.getLogger(__name__)

# Canal dédié à la détection de murs : limite le nombre de détections
# traitées en parallèle (capacité définie dans data/queue_job_data.xml)
# pour ne pas monopoliser tous les workers si plusieurs plans sont
# importés en même temps.
WALL_DETECTION_CHANNEL = "root.construction_wall_detection"


def _is_concurrency_error(exc):
    """Conflit d'accès PostgreSQL (sérialisation, verrou, interblocage).

    Ces erreurs sont transitoires : Odoo rejoue la requête entière jusqu'à
    5 fois (odoo.service.model.retrying). Les attraper dans un `except
    Exception` les transformerait en échec définitif — c'est ce qui produit
    le message « could not serialize access due to concurrent update ». On
    les laisse donc toujours remonter."""
    return (isinstance(exc, OperationalError)
            and exc.pgcode in PG_CONCURRENCY_ERRORS_TO_RETRY)


class ConstructionDwgFile(models.Model):
    _name = "construction.dwg.files" 
    _description = "Gestion des fichiers DWG"
    _rec_name = "filename"
    

    ALLOWED_EXTENSIONS = ('.dwg', '.dxf')

    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        required=True,
        ondelete="cascade",
    )

    filename = fields.Char(string="Nom du fichier", required=True)
    file = fields.Binary(string="Fichier DWG/DXF", required=True, attachment=True)
    dxf_filename = fields.Char(string="Nom du fichier DXF", readonly=True)
    dxf_file = fields.Binary(string="Fichier DXF", attachment=True, readonly=True)
    metadata_id = fields.One2many(
        "construction.dwg.metadata",
        "dwg_file_id",
        string="Métadonnées DXF",
    )
  
    layer_ids = fields.One2many(
        "construction.dwg.layer",
        "dwg_file_id",
        string="Calques",
    )
    
    block_ids = fields.One2many(
        "construction.dwg.block",
        "dwg_file_id",
        string="Blocs",
    )
    
    entity_ids = fields.One2many(
        "construction.dwg.entity",
        "dwg_file_id",
        string="Entités DXF",
    )

    annotation_ids = fields.One2many(
        "construction.dwg.annotation",
        "dwg_file_id",
        string="Annotations",
    )
    
    coordinate_system_ids = fields.One2many(
        "construction.dwg.coordinate.system",
        "dwg_file_id",
        string="Systèmes de coordonnées",
    )

    wall_ids = fields.One2many(
        "construction.wall",
        "dwg_file_id",
        string="Murs détectés"
    )
    
    wall_count = fields.Integer(
        string="Nombre de murs",
        compute="_compute_wall_count"
    )

    # ---------------------------------------------------------
    # AJOUTS : suivi de la détection de murs asynchrone
    # ---------------------------------------------------------
    wall_detection_state = fields.Selection(
        [
            ("draft", "Non lancée"),
            ("queued", "En file d'attente"),
            ("in_progress", "En cours"),
            ("done", "Terminée"),
            ("failed", "Échec"),
        ],
        default="draft",
        string="État détection des murs",
        copy=False,
    )
    wall_detection_job_id = fields.Many2one(
        "queue.job",
        string="Job de détection",
        copy=False,
        readonly=True,
    )
    wall_detection_error = fields.Text(
        string="Erreur détection des murs",
        copy=False,
        readonly=True,
    )

    merge_overlapping_walls = fields.Boolean(
        string="Regrouper les murs qui se chevauchent",
        default=True,
        help="Vue en plan : réunit en un seul mur les murs parallèles, de même "
             "épaisseur et sur le même axe qui se recouvrent (ex. : 2→12, 6→8 "
             "et 3→20 deviennent un mur 2→20). Décochez pour garder chaque "
             "morceau tel que dessiné. Pris en compte à la prochaine détection.",
    )

    imported_at = fields.Datetime(
        string="Date d'import", default=fields.Datetime.now, readonly=True
    )
    
    # utilise la table construction_dwg_files_plan_type_rel 
    plan_type_ids = fields.Many2many(
        "construction.plan.type",
        "construction_dwg_files_plan_type_rel",
        "dwg_file_id",
        "plan_type_id",
        string="Types de plan",
        help="Un plan peut cumuler plusieurs types "
             "(ex : Architectural + Coffrage).",
    )
    # utilise la table construction_dwg_files_plan_level_rel
    level_ids = fields.Many2many(
        "construction.plan.level",
        "construction_dwg_files_plan_level_rel",
        "dwg_file_id",
        "plan_level_id",
        string="Niveaux",
        help="Un plan peut couvrir plusieurs niveaux "
             "(ex : RDC + R+1 sur une coupe).",
    )
    # utilise la table construction_dwg_files_plan_view_rel
    view_ids = fields.Many2many(
        "construction.plan.view",
        "construction_dwg_files_plan_view_rel",
        "dwg_file_id",
        "plan_view_id",
        string="Types de vue",
        help="Un plan peut cumuler plusieurs types de vue "
             "(ex : Plan + Coupe).",
    )

    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("imported", "Importé"),
            ("analysed", "Analysé"),
            ("error", "Erreur"),
        ],
        default="draft",
    )

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------
    # @api.depends("wall_ids")
    # def _compute_wall_count(self):
    #     for record in self:
    #         record.wall_count = len(record.wall_ids)
            
    def _compute_wall_count(self):
        for rec in self:
            rec.wall_count = self.env["construction.wall"].search_count(
                [("dwg_file_id", "=", rec.id)]
            )
            
    def action_view_walls_visual(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/construction/walls/{self.id}",
            "target": "new",
        }

    # ---------------------------------------------------------
    # MENU « VISUALISER »
    # ---------------------------------------------------------
    # Méthodes que le menu a le droit d'appeler : le widget ne passe que par
    # `action_open_viewer`, jamais par un nom de méthode choisi côté client.
    def _viewer_menu_items(self):
        """Entrées du menu déroulant « Visualiser » de la fiche plan.

        Chaque visualiseur s'y ajoute par surcharge (super() + append) :
        la vue n'a plus à recevoir un bouton par visualiseur. Une entrée :
        {"key", "label", "icon" (font-awesome), "method", "sequence"}."""
        self.ensure_one()
        return [
            {"key": "dxf", "label": "Plan DXF", "icon": "fa-eye",
             "method": "action_visualize", "sequence": 10},
            {"key": "walls", "label": "Murs", "icon": "fa-building",
             "method": "action_view_walls_visual", "sequence": 20},
        ]

    def get_viewer_menu(self):
        """Appelé par le widget du menu : entrées disponibles, triées."""
        self.ensure_one()
        if not self.dxf_file:
            return []
        items = sorted(self._viewer_menu_items(), key=lambda i: i["sequence"])
        return [{k: item[k] for k in ("key", "label", "icon")} for item in items]

    def action_open_viewer(self, key):
        self.ensure_one()
        item = next((i for i in self._viewer_menu_items() if i["key"] == key), None)
        if not item:
            raise UserError("Visualisation inconnue : %s" % key)
        return getattr(self, item["method"])()
                
            
    # Champs de construction.wall relus pour la consolidation : le service
    # raisonne sur des dicts, il ne connaît pas l'ORM.
    _WALL_MERGE_FIELDS = [
        "match_key", "orientation", "layer", "wall_type", "material",
        "geometry_type", "start_x", "start_y", "end_x", "end_y",
        "center_x", "center_y", "points", "length", "thickness", "height",
        "confidence", "detection_method",
    ]

    def _wall_detection_context(self):
        """Classement du plan (type / vue / niveau) transmis au service : c'est
        lui qui en déduit ce qui est observable sur cette vue et comment
        rapprocher les murs de ceux déjà connus."""
        self.ensure_one()
        view = self.view_ids[:1]
        level = self.level_ids[:1]
        return PlanContext.build(
            view=view.code or view.name,
            level=level.code or level.name,
            level_label=level.name,
            plan_types=[t.code or t.name for t in self.plan_type_ids],
            title=self.filename,
        )

    def _walls_to_consolidate(self, level):
        """Murs déjà connus du même projet au même niveau : ce sont eux que le
        plan importé vient compléter."""
        self.ensure_one()
        return self.env["construction.wall"].search([
            ("project_id", "=", self.project_id.id),
            ("level_id", "=", level.id if level else False),
        ])

    def _resolve_wall_levels(self, detected_walls):
        """Rattache chaque mur détecté à un niveau réel et finalise sa clé
        d'identité.

        Un plan de façade classique montre plusieurs étages à la fois (un mur
        par étage, séparés par la dalle) : le service ne connaît que leur
        position — 0 pour le plus bas du bloc, 1 pour le suivant... — pas vos
        niveaux. On la résout ici contre `level_ids`, trié par élévation
        croissante (le champ `elevation` de construction.plan.level) : c'est
        pourquoi le fichier doit avoir TOUS les niveaux couverts par le plan
        sélectionnés sur `level_ids`, pas seulement un.

        Les murs sans étage (vue en plan, coupe) gardent le niveau unique déjà
        posé par le service via le contexte — inchangé."""
        self.ensure_one()
        ordered_levels = self.level_ids.sorted(key=lambda l: l.elevation)

        by_level = {}
        for wall in detected_walls:
            if wall.floor_index is None:
                level = self.level_ids[:1]
            elif wall.floor_index < len(ordered_levels):
                level = ordered_levels[wall.floor_index]
                level_key = normalize_text(level.code or level.name)
                wall.match_key = "%s|%s" % (level_key, wall.match_key)
            else:
                level = self.env["construction.plan.level"]
                _logger.warning(
                    "%s : étage %d détecté sans niveau correspondant sélectionné "
                    "sur le fichier (%d niveau(x) sélectionné(s)) — mur ignoré "
                    "pour le rattachement, ajoutez le niveau manquant.",
                    self.filename, wall.floor_index, len(ordered_levels))
                wall.match_key = "sans-niveau-%d|%s" % (wall.floor_index, wall.match_key)

            by_level.setdefault(level, []).append(wall)

        return by_level

    def _detect_walls_from_dxf(self):
        """Logique métier de détection des murs. Ne fait QUE le calcul + la
        mise à jour des enregistrements construction.wall — elle ne sait rien
        de l'asynchronisme, c'est _detect_walls_job qui l'entoure de la
        gestion d'état pour le mode asynchrone."""

        self.ensure_one()

        if not self.dxf_file:
            raise UserError("Aucun fichier DXF disponible pour la détection des murs.")

        context = self._wall_detection_context()

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(base64.b64decode(self.dxf_file))
            tmp_path = tmp.name

        try:
            service = WallDetectionService(
                tmp_path, context=context,
                merge_overlaps=self.merge_overlapping_walls)
            detected_walls = service.detect_walls()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return self._apply_detected_walls(detected_walls)

    def _apply_detected_walls(self, detected_walls):
        """Applique le plan de consolidation calculé par le service : ce que
        cette vue observe complète les murs du niveau, sans jamais écraser ce
        qu'une autre vue avait déjà renseigné.

        Un plan de façade classique désigne PLUSIEURS niveaux dans un même
        fichier (un mur par étage) : on résout donc le niveau réel mur par
        mur (`_resolve_wall_levels`), et on consolide séparément dans chaque
        niveau — un mur du RDC ne doit jamais se comparer à un mur du R+1."""
        self.ensure_one()
        Wall = self.env["construction.wall"]
        view = self.view_ids[:1]

        # Relance de l'analyse : on repart de zéro pour les murs que ce plan
        # est seul à connaître, mais on conserve ceux que d'autres plans ont
        # complétés (leurs champs seront simplement recalculés ci-dessous).
        own_walls = Wall.search([("dwg_file_id", "=", self.id)])
        own_walls.filtered(lambda w: not (w.source_file_ids - self)).unlink()

        traceability = {"source_file_ids": [Command.link(self.id)]}
        if view:
            traceability["source_view_ids"] = [Command.link(view.id)]

        created = Wall
        total_updated = 0
        for level, walls_for_level in self._resolve_wall_levels(detected_walls).items():
            existing = self._walls_to_consolidate(level)
            merge_plan = merge_detected_walls(
                existing.read(self._WALL_MERGE_FIELDS), walls_for_level)

            for wall_id, vals in merge_plan.updates:
                Wall.browse(wall_id).write({**vals, **traceability})
            total_updated += len(merge_plan.updates)

            created |= Wall.create([
                dict(vals,
                     dwg_file_id=self.id,
                     level_id=level.id or False,
                     **traceability)
                for vals in merge_plan.creates
            ])

        _logger.info(
            "%s (vue %s) : %d murs créés, %d murs complétés",
            self.filename, view.name or "plan", len(created), total_updated)
        return created

    # ---------------------------------------------------------
    # AJOUTS : enfilage + corps du job asynchrone
    # ---------------------------------------------------------

    def _enqueue_wall_detection(self, description=None):
        """Enfile la détection de murs comme job queue_job au lieu de
        l'exécuter dans la transaction courante. Appelée depuis le bouton
        manuel (action_detect_walls) et depuis le pipeline d'extraction
        automatique (_extract_dxf_metadata)."""
        self.ensure_one()

        if not self.dxf_file:
            raise UserError("Aucun fichier DXF disponible pour la détection des murs.")

        if self.wall_detection_state in ("queued", "in_progress"):
            _logger.info(
                "Détection de murs déjà en cours pour %s, pas de nouvel enfilage",
                self.filename,
            )
            return False

        self.wall_detection_state = "queued"
        self.wall_detection_error = False

        delayable = self.with_delay(
            channel=WALL_DETECTION_CHANNEL,
            description=description or f"Détection des murs — {self.filename}",
            max_retries=2,
        )
        job = delayable._detect_walls_job()
        self.wall_detection_job_id = job.db_record().id
        return True

    def _detect_walls_job(self):
        """Corps exécuté par le worker queue_job, dans SA PROPRE
        transaction — indépendante de la requête HTTP qui a déclenché
        l'enfilage (create() ou clic sur le bouton). C'est ce qui règle
        le conflit de verrou observé avec le cron d'auto-vacuum sur
        ir_attachment : le calcul ne retient plus le curseur de la
        requête utilisateur pendant 10-60s."""
        self.ensure_one()
        self.wall_detection_state = "in_progress"
        # Commit immédiat pour que l'utilisateur voie "En cours" dans l'UI
        # pendant que le calcul tourne, plutôt que l'ancien état "queued".
        self.env.cr.commit()

        try:
            self._detect_walls_from_dxf()
            self.wall_detection_state = "done"
            self.wall_detection_error = False

            # Les murs rejoignent le circuit commun de validation : ils
            # deviennent des éléments à valider, comme les semelles.
            self._enqueue_analysis_wall_elements()

            # Si les autres extractions (métadonnées/calques/annotations/...)
            # avaient déjà réussi, on complète l'état global maintenant que
            # les murs sont là aussi.
            if self.state == "imported":
                self.state = "analysed"

        except Exception as exc:
            _logger.exception("Échec de la détection de murs pour %s", self.filename)
            self.wall_detection_state = "failed"
            self.wall_detection_error = str(exc)
            # On relève : queue_job marque le job "failed" et applique le
            # retry (max_retries=2 défini dans _enqueue_wall_detection).
            raise

        return True

    def _wall_detection_related_action(self):
        """Related action du job : clic sur le job dans la vue queue.job
        -> ouvre directement ce plan DWG."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_detect_walls(self):
        """Bouton manuel : enfile la détection au lieu de l'exécuter
        directement, et notifie l'utilisateur au lieu d'ouvrir la liste
        des murs (qui n'existent pas encore au moment du clic)."""
        self.ensure_one()
        context = self._wall_detection_context()
        if not context.is_supported:
            raise UserError(
                "La vue « %s » ne montre pas les murs : choisissez un plan en vue "
                "Plan, Façade ou Coupe." % (self.view_ids[:1].name or context.view))
        try:
            self._enqueue_wall_detection()
        except Exception as exc:
            _logger.exception("Échec de l'enfilage de la détection des murs sur %s", self.filename)
            raise UserError(f"Erreur lors de l'enfilage de l'analyse : {exc}") from exc

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Détection des murs lancée",
                "message": (
                    "Le traitement se fait en arrière-plan. "
                    "Rafraîchissez la fiche pour suivre l'avancement."
                ),
                "sticky": False,
                "type": "info",
            },
        }
               
    def _check_dwg_signature(self, file_bytes):
        """Vérifie que le fichier est bien un DWG valide via sa signature binaire."""
        if file_bytes[:2] != b'AC':
            raise ValidationError(
                "Le fichier ne semble pas être un fichier DWG valide (signature invalide)."
            )

    def _check_dxf_signature(self, file_bytes):
        """Vérifie sommairement qu'un fichier DXF a l'air valide (fichier texte ASCII)."""
        try:
            file_bytes[:50].decode('ascii')
        except UnicodeDecodeError:
            raise ValidationError(
                "Le fichier ne semble pas être un fichier DXF valide (contenu non-ASCII détecté)."
            )

    
    @api.constrains('filename', 'file')
    def _check_file_content(self):
        for record in self:
            if not record.filename or not record.file:
                continue
            ext = Path(record.filename).suffix.lower()
            if ext not in self.ALLOWED_EXTENSIONS:
                raise ValidationError(
                    f"Extension non autorisée : '{ext}'. "
                    f"Formats acceptés : {', '.join(self.ALLOWED_EXTENSIONS)}"
                )
            file_bytes = base64.b64decode(record.file)
            if ext == '.dwg':
                record._check_dwg_signature(file_bytes)
            elif ext == '.dxf':
                record._check_dxf_signature(file_bytes)

    # ---------------------------------------------------------
    # Traitement du fichier (conversion ou copie directe)
    # ---------------------------------------------------------
    
    
    def action_process_file(self):
        """Point d'entrée : convertit si DWG, copie directement si DXF."""
        for record in self:
            try:
                # Le savepoint garantit que le curseur reste utilisable en cas
                # d'erreur SQL : sans lui, le `write` ci-dessous échouerait à
                # son tour et l'utilisateur ne verrait jamais la vraie cause.
                with self.env.cr.savepoint():
                    ext = Path(record.filename).suffix.lower()
                    if ext == '.dwg':
                        record._convert_dwg_to_dxf()
                    elif ext == '.dxf':
                        record._store_dxf_directly()
                    else:
                        raise UserError(f"Extension non gérée : {ext}")
                    record.state = "imported"
                    record._extract_dxf_metadata()
            except Exception as e:
                if _is_concurrency_error(e):
                    raise
                record.state = "error"
                _logger.exception("Erreur de traitement pour %s", record.filename)
                raise UserError(f"Erreur lors du traitement : {e}")
        
        
    def _extract_dxf_metadata(self):
        """Extrait les métadonnées, calques, blocs, entités et murs du DXF
        généré. Chaque extraction est indépendante : l'échec de l'une
        n'empêche pas les autres."""
        self.ensure_one()

        extractions = [
            ('construction.dwg.metadata', 'métadonnées'),
            ('construction.dwg.layer', 'calques'),
            ('construction.dwg.block', 'blocs'),
            ('construction.dwg.entity', 'entités'),
            ('construction.dwg.annotation', 'annotations'),
            ('construction.dwg.coordinate.system', 'systèmes de coordonnées'),
        ]

        all_ok = True
        for model_name, label in extractions:
            try:
                # Point de sauvegarde obligatoire : sans lui, une erreur SQL
                # attrapée ici laisse la transaction inutilisable, et c'est le
                # flush de fin de requête qui échoue — sur un message sans
                # rapport (« current transaction is aborted »). Avec, seule
                # l'extraction fautive est annulée.
                with self.env.cr.savepoint():
                    self.env[model_name].extract_from_dwg_file(self)
            except Exception as exc:
                if _is_concurrency_error(exc):
                    raise
                all_ok = False
                _logger.exception(
                    "Extraction des %s échouée pour %s", label, self.filename
                )

        # MODIFIÉ : la détection des murs n'est plus exécutée ici de façon
        # synchrone (c'était elle qui bloquait la transaction de create()
        # pendant 10-60s et entrait en conflit de verrou avec les crons —
        # cf. logs "lock timeout" sur ir_attachment). On se contente
        # désormais de l'enfiler ; son propre état est suivi séparément
        # via wall_detection_state, et vient compléter `state` à "analysed"
        # une fois le job terminé (voir _detect_walls_job).
        # MODIFIÉ (analyse selon le type de plan) : au lieu de toujours lancer
        # la détection de murs, on enfile les analyses associées aux types de
        # plan du fichier (ARCH -> murs, FOND/COFF -> éléments...). Sans type de
        # plan renseigné, comportement historique conservé (murs).
        # Voir construction_file_ext.py : _auto_enqueue_analyses().
        try:
            with self.env.cr.savepoint():
                self._auto_enqueue_analyses()
        except Exception as exc:
            if _is_concurrency_error(exc):
                raise
            all_ok = False
            _logger.exception(
                "Enfilage des analyses échoué pour %s", self.filename
            )

        # NOTE : "analysed" ici ne couvre que les extractions synchrones
        # ci-dessus. L'état inclura les murs une fois le job terminé
        # (cf. _detect_walls_job qui repasse "imported" -> "analysed").
        self.state = "analysed" if all_ok else "imported"
                
            
    def _store_dxf_directly(self):
        """Cas où le fichier importé est déjà un DXF : pas de conversion nécessaire."""
        self.ensure_one()
        self.dxf_filename = self.filename
        self.dxf_file = self.file  # déjà en base64, on copie tel quel

    def _convert_dwg_to_dxf(self):
        """Cas où le fichier importé est un DWG : conversion via ODA File Converter."""
        self.ensure_one()
        oda_path = self.env['ir.config_parameter'].sudo().get_param(
            'construction_dwg.oda_paths' 
        )

        if not oda_path or not Path(oda_path).exists():
            raise UserError(
                "Le chemin vers ODA File Converter n'est pas configuré ou est invalide. "
                "Vérifiez le paramètre système 'construction_dwg.oda_path'."
            )

        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            input_dir.mkdir()
            output_dir.mkdir()

            dwg_path = input_dir / self.filename
            dwg_path.write_bytes(base64.b64decode(self.file))

            command = [
                oda_path,
                str(input_dir),
                str(output_dir),
                "ACAD2018",
                "DXF",
                "0",   # pas de recherche récursive
                "1",   # audit
                "*.dwg",
            ]
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                raise UserError(
                    f"ODA Converter a échoué (code {result.returncode}) : {result.stderr}"
                )

            dxf_files = list(output_dir.glob("*.dxf"))
            if not dxf_files:
                raise UserError("Aucun fichier DXF n'a été généré.")

            dxf_path = dxf_files[0]
            self.dxf_filename = dxf_path.name
            self.dxf_file = base64.b64encode(dxf_path.read_bytes())

            
    def action_visualize(self):
        self.ensure_one()

        if not self.dxf_file:
            raise UserError(
                "Aucun fichier DXF disponible pour ce document. "
                "Vérifiez que le fichier a bien été traité."
            )
        
        construction_frontend_url = config.get(
            'construction_frontend_url' 
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"{construction_frontend_url}/viewer/{self.id}",
            "target": "new",
        }
        

    # ---------------------------------------------------------
    # Création
    # ---------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.action_process_file()
        return records