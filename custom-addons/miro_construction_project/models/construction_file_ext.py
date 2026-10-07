import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ConstructionDwgFile(models.Model):
    _inherit = 'construction.dwg.files'

    analysis_ids = fields.One2many('construction.analysis', 'file_id', string="Analyses éléments")
    analysis_count = fields.Integer(compute='_compute_analysis_count')
    element_analysis_available = fields.Boolean(
        string="Analyse d'éléments possible",
        compute='_compute_element_analysis_available',
        help="Au moins un type d'élément est configuré pour les types de plan de ce "
             "fichier. Sinon, l'analyse d'éléments ne pourrait rien trouver.")

    is_execution_plan = fields.Boolean(
        "Plan d'exécution", compute='_compute_is_execution_plan',
        help="Au moins un type de plan du fichier est de la famille "
             "« Exécution » : ses ouvrages deviennent éléments, tâches et phases.")

    @api.depends('plan_type_ids.plan_family')
    def _compute_is_execution_plan(self):
        for rec in self:
            rec.is_execution_plan = 'execution' in rec.plan_type_ids.mapped('plan_family')

    def _compute_analysis_count(self):
        for rec in self:
            rec.analysis_count = len(rec.analysis_ids)

    @api.depends('plan_type_ids', 'block_ids')
    def _compute_element_analysis_available(self):
        for rec in self:
            rec.element_analysis_available = bool(
                rec.block_ids and rec._eligible_element_types())

    # ------------------------------------------------------------------
    # Aiguillage : type de plan -> analyse(s) à lancer
    # ------------------------------------------------------------------
    def _get_analyzer_codes(self):
        """Codes d'analyse déduits des types de plan (union, sans doublon)."""
        self.ensure_one()
        return sorted({c for c in self.plan_type_ids.mapped('analyzer') if c and c != 'none'})

    def _auto_enqueue_analyses(self, strict=False):
        """Enfile l'analyse de chaque type de plan. Retourne la liste des codes lancés.

        - strict=False (import auto) : sans type de plan, comportement historique (murs).
        - strict=True  (bouton)      : sans type de plan, erreur explicite.
        """
        self.ensure_one()
        if not self.plan_type_ids:
            if strict:
                raise UserError(_("Renseignez au moins un type de plan sur ce fichier."))
            self._enqueue_analysis_walls()
            return ['walls']

        launched = []
        for code in self._get_analyzer_codes():
            method = getattr(self, '_enqueue_analysis_%s' % code, None)
            if not method:
                _logger.warning("Aucune méthode _enqueue_analysis_%s pour %s", code, self.filename)
                continue
            if method():
                launched.append(code)
        return launched

    def _enqueue_analysis_walls(self):
        """Analyse « Détection de murs » (plans architecturaux) : service existant.

        Une vue dont on ne sait rien tirer (détail, schéma, 3D) n'est pas
        enfilée : c'est le service qui dit ce qu'une vue permet d'observer."""
        self.ensure_one()
        if not self._wall_detection_context().is_supported:
            _logger.info(
                "Vue « %s » non exploitable pour la détection de murs : %s ignoré",
                self.view_ids[:1].name or "?", self.filename)
            return False
        return self._enqueue_wall_detection(
            description=_("Détection des murs (auto) — %s") % self.filename)

    def _enqueue_analysis_elements(self, strict=False):
        """Analyse « Éléments » (fondation, coffrage...) : construction.analysis."""
        self.ensure_one()
        if not self.block_ids:
            _logger.info("Pas de blocs extraits pour %s : analyse d'éléments ignorée", self.filename)
            if strict:
                raise UserError(_(
                    "Aucun bloc extrait pour ce plan. Traitez d'abord le fichier "
                    "(bouton « Traiter / Convertir »)."))
            return False
        if not strict and not self._eligible_element_types():
            _logger.info("Aucun type d'élément applicable aux types de plan de %s", self.filename)
            return False
        if self.analysis_ids.filtered(lambda a: a.state == 'running'):
            return False
        analysis = self.env['construction.analysis'].create({
            'file_id': self.id,
            'revision': self.filename,
        })
        analysis.action_start()
        return analysis

    def _enqueue_analysis_wall_elements(self):
        """Fait remonter les murs détectés dans le circuit de validation :
        analyse -> brouillons -> éléments -> phases.

        Appelée à la fin de la détection (cf. _detect_walls_job), une fois les
        murs écrits et complétés. Relancer une détection relance l'analyse :
        les brouillons déjà validés ne sont jamais réécrits.

        Sans mur à faire valider, aucune analyse n'est créée : elle échouerait
        aussitôt sur « Aucun mur détecté pour ce plan », ce qui signalerait
        une erreur là où il n'y a qu'un plan sans mur (un plan de fondation,
        par exemple, n'en porte aucun)."""
        self.ensure_one()
        if not self.is_execution_plan:
            # Plan de référence (architecture) : les murs restent détectés et
            # complètent les autres plans, mais ne deviennent pas des tâches.
            _logger.info("%s : plan de référence, murs non soumis à validation",
                         self.filename)
            return False
        if self.analysis_ids.filtered(
                lambda a: a.state == 'running' and a.engine == 'walls'):
            return False

        if not self.env['construction.wall'].search_count([
                '|', ('dwg_file_id', '=', self.id),
                     ('source_file_ids', 'in', self.id)]):
            _logger.info("Aucun mur sur %s : pas d'analyse d'éléments murs",
                         self.filename)
            return False

        analysis = self.env['construction.analysis'].create({
            'file_id': self.id,
            'revision': self.filename,
            'engine': 'walls',
        })
        analysis.action_start()
        return analysis

    def _enqueue_analysis_footings(self, strict=False):
        """Analyse « Fondations » : semelles et longrines lues dans la
        géométrie des calques (S-SEM, S-SEM-FIL, S-LON), sans passer par les
        blocs DXF. Alimente les mêmes brouillons d'éléments."""
        self.ensure_one()
        if self.analysis_ids.filtered(
                lambda a: a.state == 'running' and a.engine == 'footings'):
            return False
        analysis = self.env['construction.analysis'].create({
            'file_id': self.id,
            'revision': self.filename,
            'engine': 'footings',
        })
        analysis.action_start()
        return analysis

    def _enqueue_analysis_formwork(self):
        """Analyse « Coffrage » : poteaux, poutres, dalles et murs lus dans la
        géométrie des calques S-POT, S-POU, S-DAL/S-TREMIE et S-REF."""
        return self._enqueue_engine_analysis('formwork')

    def _enqueue_analysis_details(self):
        """Analyse « Coupes et détails » : profil structurel (hauteurs
        d'étage, épaisseurs, sections, ferraillage) qui complète les
        brouillons des autres plans d'exécution du projet."""
        return self._enqueue_engine_analysis('details')

    def _enqueue_engine_analysis(self, engine):
        self.ensure_one()
        if self.analysis_ids.filtered(
                lambda a: a.state == 'running' and a.engine == engine):
            return False
        analysis = self.env['construction.analysis'].create({
            'file_id': self.id,
            'revision': self.filename,
            'engine': engine,
        })
        analysis.action_start()
        return analysis

    def _eligible_element_types(self):
        """Types d'éléments cherchables sur ce plan : ils ont un mot-clé DXF et leurs
        « types de plan concernés » recoupent ceux du fichier (vide = tous)."""
        self.ensure_one()
        types = self.env['construction.element.type'].search([
            '|', ('dxf_block_keyword', '!=', False), ('dxf_layer_keyword', '!=', False)])
        if self.plan_type_ids:
            types = types.filtered(
                lambda t: not t.plan_type_ids or (t.plan_type_ids & self.plan_type_ids))
        return types

    # ------------------------------------------------------------------
    # Boutons
    # ------------------------------------------------------------------
    def action_run_typed_analyses(self):
        """Lance les analyses correspondant aux types de plan du fichier."""
        self.ensure_one()
        launched = self._auto_enqueue_analyses(strict=True)
        labels = dict(self.env['construction.plan.type']._fields['analyzer'].selection)
        message = (_("Analyses lancées : %s") % ", ".join(labels[c] for c in launched)
                   if launched else
                   _("Aucune analyse à lancer pour les types de plan de ce fichier "
                     "(déjà en cours, ou aucune analyse configurée)."))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _("Analyse par type de plan"), 'message': message,
                       'sticky': False, 'type': 'info'},
        }

    def action_analyze_elements(self):
        """Force l'analyse d'éléments (quel que soit le type de plan) et ouvre la fiche."""
        self.ensure_one()
        if not self._eligible_element_types():
            raise UserError(_(
                "Aucun type d'élément ne s'applique aux types de plan de ce fichier (%s). "
                "Cette analyse ne lit QUE les blocs DXF (INSERT) : elle ne convient "
                "qu'aux plans dont les ouvrages sont dessinés comme des blocs nommés. "
                "Pour un plan de fondation (calques S-SEM, S-POT, S-SEM-FIL, S-LON), "
                "utilisez « Analyses par type de plan », qui lance la détection des "
                "fondations à partir de la géométrie. Pour un plan architectural, "
                "utilisez « Détecter les murs ».")
                % (', '.join(self.plan_type_ids.mapped('code')) or _("aucun")))
        analysis = self._enqueue_analysis_elements(strict=True)
        if not analysis:
            raise UserError(_("Une analyse d'éléments est déjà en cours pour ce plan."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'construction.analysis',
            'res_id': analysis.id,
            'view_mode': 'form',
        }

    def action_view_analyses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Analyses éléments"),
            'res_model': 'construction.analysis',
            'view_mode': 'tree,form',
            'domain': [('file_id', '=', self.id)],
            'context': {'default_file_id': self.id},
        }

    def _viewer_menu_items(self):
        items = super()._viewer_menu_items()
        items.append({"key": "footings", "label": _("Éléments structurels"), "icon": "fa-th",
                      "method": "action_view_footings_visual", "sequence": 30})
        return items

    def action_view_footings_visual(self):
        """Ouvre le plan de visualisation des éléments de fondation validés
        (construction.element) de ce fichier. Un brouillon encore en attente
        n'y apparaît pas : voir « Éléments à valider » pour ceux-là."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/construction/footings/{self.id}",
            "target": "new",
        }
