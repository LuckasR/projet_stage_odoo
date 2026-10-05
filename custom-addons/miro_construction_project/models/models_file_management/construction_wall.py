import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Champs du mur qui alimentent les cotes et métrés de son élément.
SYNC_FIELDS = {"length", "thickness", "height"}


class ConstructionWall(models.Model):
    _name = "construction.wall"
    _description = "Mur détecté"
    _order = "id desc"

    # =========================
    # IDENTIFICATION
    # =========================
    name = fields.Char(
        string="Nom",
        required=True,
        default="Nouveau mur"
    )
    active = fields.Boolean(
        string="Actif",
        default=True
    )
    dwg_file_id = fields.Many2one(
        "construction.dwg.files",
        string="Plan d'origine",
        required=True,
        ondelete="cascade",
        index=True,
        help="Plan qui a fait apparaître ce mur pour la première fois.",
    )
    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        related="dwg_file_id.project_id",
        store=True,
        index=True,
        readonly=True,
    )
    level_id = fields.Many2one(
        "construction.plan.level",
        string="Niveau",
        index=True,
    )
    facade_id = fields.Many2one(
        "construction.facade",
        string="Façade",
        ondelete="set null",
        index=True,
        help="Façade sur laquelle ce mur a été relevé. Renseignée par la "
             "détection de façade, qui regroupe les murs extérieurs d'une même "
             "orientation sans les dupliquer.",
    )
    match_key = fields.Char(
        string="Clé d'identification",
        index=True,
        copy=False,
        help="Identité du mur dans le niveau (ex. : r+0|facade-nord). Permet à un "
             "plan d'une autre vue de compléter ce mur au lieu d'en créer un second.",
    )
    source_file_ids = fields.Many2many(
        "construction.dwg.files",
        "construction_wall_source_file_rel",
        "wall_id",
        "dwg_file_id",
        string="Plans sources",
        help="Tous les plans qui ont renseigné une partie de ce mur.",
    )
    source_view_ids = fields.Many2many(
        "construction.plan.view",
        "construction_wall_source_view_rel",
        "wall_id",
        "plan_view_id",
        string="Vues sources",
        help="Types de vue ayant permis d'observer ce mur (plan, façade, coupe...).",
    )

    # =========================
    # CLASSIFICATION
    # =========================
    orientation = fields.Selection([
        ("nord", "Nord"),
        ("sud", "Sud"),
        ("est", "Est"),
        ("ouest", "Ouest"),
    ], string="Orientation",
        help="Façade sur laquelle donne le mur. Sert à rapprocher un mur vu en "
             "façade du même mur vu en plan.")

    wall_type = fields.Selection([
        ("exterior", "Mur extérieur"),
        ("interior", "Mur intérieur"),
        ("partition", "Cloison"),
        ("load_bearing", "Mur porteur"),
        ("retaining", "Mur de soutènement"),
        ("unknown", "Inconnu"),
    ], string="Type de mur", default="unknown")

    material = fields.Selection([
        ("concrete", "Béton"),
        ("brick", "Brique"),
        ("block", "Parpaing"),
        ("other", "Autre"),
        ("unknown", "Inconnu"),
    ], string="Matériau", default="unknown")

    # =========================
    # SOURCE DXF
    # =========================
    layer = fields.Char(
        string="Calque",
        index=True
    )

    # =========================
    # GÉOMÉTRIE
    # =========================
    geometry_type = fields.Selection([
        ("line",            "Ligne"),
        ("polyline_open",   "Polyligne ouverte"),
        ("polyline_closed", "Polyligne fermée"),
        ("polyline",        "Polyligne (générique)"),   # conservé pour compat
        ("polygon",         "Polygone"),
        ("line_pair",       "Deux lignes parallèles"),
        ("unknown",         "Inconnu"),
    ], string="Type de géométrie", default="unknown")
    
    start_x = fields.Float(string="Début X")
    start_y = fields.Float(string="Début Y")
    end_x = fields.Float(string="Fin X")
    end_y = fields.Float(string="Fin Y")
    center_x = fields.Float(string="Centre X")
    center_y = fields.Float(string="Centre Y")

    # Pour polylignes / polygones à plusieurs sommets
    points = fields.Text(
        string="Points (JSON)",
        help="Liste de coordonnées [[x1,y1],[x2,y2],...] utilisée pour "
             "les polylignes et polygones, en complément de start/end/center."
    )

    length = fields.Float(
        string="Longueur",
        help="Longueur du mur en mètres"
    )
    thickness = fields.Float(
        string="Épaisseur",
        help="Épaisseur du mur en mètres"
    )
    height = fields.Float(
        string="Hauteur",
        help="Hauteur du mur en mètres"
    )

    # =========================
    # MÉTRÉS
    # =========================
    area = fields.Float(
        string="Surface",
        compute="_compute_metrics",
        store=True
    )
    volume = fields.Float(
        string="Volume",
        compute="_compute_metrics",
        store=True
    )

    # =========================
    # ANALYSE
    # =========================
    confidence = fields.Float(
        string="Confiance (%)",
        digits=(5, 2),
        help="Niveau de confiance de la détection entre 0 et 100"
    )
    detection_method = fields.Selection([
        ("layer", "Calque"),
        ("geometry", "Géométrie"),
        ("combined", "Calque + Géométrie"),
    ], string="Méthode de détection", default="geometry")

    # =========================
    # VALIDATION
    # =========================
    is_validated = fields.Boolean(
        string="Validé",
        default=False
    )

    # =========================
    # ÉLÉMENT DE CONSTRUCTION
    # =========================
    # Le mur est la donnée technique tirée du dessin ; l'élément est l'ouvrage
    # du chantier (phases, avancement, chiffrage). Le lien est posé par le
    # moteur d'analyse « murs » et suivi par _sync_elements.
    element_ids = fields.One2many(
        "construction.element", "wall_id", string="Éléments de construction")
    draft_ids = fields.One2many(
        "construction.element.draft", "wall_id", string="Brouillons d'éléments")
    element_id = fields.Many2one(
        "construction.element", string="Élément de construction",
        compute="_compute_element_id",
        help="Ouvrage validé qui représente ce mur. Vide tant que son "
             "brouillon n'a pas été validé puis généré.")

    # =========================
    # CONTRAINTES SQL
    # =========================
    _sql_constraints = [
        (
            "length_positive",
            "CHECK(length >= 0)",
            "La longueur du mur doit être positive ou nulle."
        ),
        (
            "thickness_positive",
            "CHECK(thickness >= 0)",
            "L'épaisseur du mur doit être positive ou nulle."
        ),
        (
            "height_positive",
            "CHECK(height >= 0)",
            "La hauteur du mur doit être positive ou nulle."
        ),
    ]

    # =========================
    # CONTRAINTES PYTHON
    # =========================
    @api.constrains("confidence")
    def _check_confidence(self):
        for wall in self:
            if wall.confidence and not (0 <= wall.confidence <= 100):
                raise ValidationError(
                    "Le niveau de confiance doit être compris entre 0 et 100."
                )

    # =========================
    # CALCULS
    # =========================
    @api.depends("length", "thickness", "height")
    def _compute_metrics(self):
        for wall in self:
            wall.area = wall.length * wall.height
            wall.volume = wall.length * wall.thickness * wall.height
    @api.depends("element_ids")
    def _compute_element_id(self):
        for wall in self:
            wall.element_id = wall.element_ids[:1]

    # =========================
    # SYNCHRONISATION MUR -> ÉLÉMENT
    # =========================
    def write(self, vals):
        res = super().write(vals)
        if SYNC_FIELDS & set(vals):
            self._sync_elements()
        return res

    def _sync_elements(self):
        """Reporte les cotes et métrés du mur sur ses brouillons non encore
        générés et sur ses éléments de construction.

        Les valeurs passent par `_wall_to_item`, le même calcul que l'analyse :
        un élément synchronisé est donc identique à celui qu'une nouvelle
        analyse aurait produit, sans avoir à la relancer ni à revalider."""
        Analysis = self.env["construction.analysis"]
        for wall in self:
            if not (wall.element_ids or wall.draft_ids):
                continue
            item = Analysis._wall_to_item(wall)

            # Validé mais pas encore généré : la génération recopiera le
            # brouillon dans l'élément, il doit donc être à jour lui aussi.
            drafts = wall.draft_ids.filtered(
                lambda d: d.state in ("pending", "validated"))
            for draft in drafts:
                dims = dict(draft.dimensions or {})
                dims.update(item["dimensions"])
                quantities = dict(draft.quantities or {})
                quantities.update(item["quantities"])
                draft.write({
                    "dimensions": dims,
                    "quantities": quantities,
                    "issue": item["issue"],
                    "confidence": item["confidence"],
                })

            wall.element_ids._apply_wall_measures(item)

    @api.model
    def _link_elements(self):
        """Rattrapage à la mise à jour du module : relie aux murs les
        brouillons et éléments créés avant l'existence du lien, en
        retrouvant leur clé (MUR-...), puis les resynchronise. Idempotent."""
        Analysis = self.env["construction.analysis"]
        Draft = self.env["construction.element.draft"]
        Element = self.env["construction.element"].with_context(active_test=False)

        linked = self.browse()
        for wall in self.with_context(active_test=False).search([]):
            key = Analysis._wall_key(wall)
            files = wall.dwg_file_id | wall.source_file_ids
            drafts = Draft.search([
                ("wall_id", "=", False),
                ("type_code", "=", "mur"),
                ("key", "=", key),
                ("level_id", "=", wall.level_id.id),
                ("analysis_id.file_id", "in", files.ids),
            ])
            elements = Element.search([
                ("wall_id", "=", False),
                ("key", "=", key),
                ("level_id", "=", wall.level_id.id),
                ("project_id", "=", wall.project_id.id),
            ]) if wall.project_id else Element
            if drafts or elements:
                drafts.write({"wall_id": wall.id})
                elements.write({"wall_id": wall.id})
                linked |= wall

        if linked:
            linked._sync_elements()
            _logger.info("%d mur(s) reliés à leurs éléments de construction",
                         len(linked))

    def action_open_element(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Élément de construction"),
            "res_model": "construction.element",
            "res_id": self.element_id.id,
            "view_mode": "form",
        }
