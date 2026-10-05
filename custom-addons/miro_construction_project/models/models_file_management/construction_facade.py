# -*- coding: utf-8 -*-
"""Stockage de ce qu'un plan de façade décrit du bâtiment.

Une façade est l'unité de relevé : tout ce que le plan montre s'y rattache.

    construction.facade                 la façade et son emprise
      ├── construction.facade.level     bandes d'étage séparées par les dalles
      ├── construction.wall             murs (modèle existant, via facade_id)
      ├── construction.facade.opening   portes, fenêtres, baies
      ├── construction.facade.feature   balcon, garde-corps, corniche, toiture
      ├── construction.facade.dimension cotes horizontales / verticales / altimétriques
      └── construction.facade.annotation textes, repères, matériaux

Les murs ne sont pas dupliqués ici : ils vivent dans construction.wall, où
ils se complètent d'une vue à l'autre (une façade donne la hauteur, une vue
en plan donne l'épaisseur). La façade ne fait que les regrouper.

Toutes les longueurs sont en mètres. Les hauteurs d'allège, de linteau et de
bande d'étage sont comptées depuis le BAS de la façade : les dessinateurs ne
placent pas tous l'origine du dessin au même endroit, seule cette référence
est comparable d'un plan à l'autre.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Écart au-delà duquel deux façades validées ne s'accordent pas sur la hauteur
# d'un même niveau : au-delà, l'une des deux détections est fausse.
LEVEL_HEIGHT_TOLERANCE = 0.05

# Matériaux reconnus dans les annotations (cf. MATERIAL_KEYWORDS du service).
MATERIALS = [
    ("concrete", "Béton"),
    ("brick", "Brique"),
    ("block", "Parpaing"),
    ("stone", "Pierre"),
    ("wood", "Bois"),
    ("metal", "Métal / Aluminium"),
    ("pvc", "PVC"),
    ("glass", "Verre"),
    ("render", "Enduit"),
    ("other", "Autre"),
    ("unknown", "Inconnu"),
]

ORIENTATIONS = [
    ("nord", "Nord"),
    ("sud", "Sud"),
    ("est", "Est"),
    ("ouest", "Ouest"),
]


class ConstructionFacade(models.Model):
    _name = "construction.facade"
    _description = "Façade relevée sur un plan"
    _order = "project_id, orientation, name"

    # =========================
    # IDENTIFICATION
    # =========================
    name = fields.Char("Nom", required=True, default="Nouvelle façade")
    mark = fields.Char(
        "Repère",
        help="Repère porté au dessin (ex. : FA-01). Libre si le plan n'en donne pas.")
    drawing_number = fields.Char(
        "Numéro du dessin",
        help="Numéro relevé dans le cartouche (« N° A-04 »).")
    orientation = fields.Selection(
        ORIENTATIONS, string="Orientation",
        help="Façade sur laquelle donne le mur. Sert à rapprocher cette façade "
             "des murs vus en plan.")
    active = fields.Boolean("Actif", default=True)

    dwg_file_id = fields.Many2one(
        "construction.dwg.files", string="Plan d'origine",
        required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(
        "project.project", string="Projet",
        related="dwg_file_id.project_id", store=True, index=True, readonly=True)
    source_file_ids = fields.Many2many(
        "construction.dwg.files", "construction_facade_source_file_rel",
        "facade_id", "dwg_file_id", string="Plans sources",
        help="Tous les plans qui ont renseigné une partie de cette façade.")
    match_key = fields.Char(
        "Clé d'identification", index=True, copy=False,
        help="Identité de la façade (ex. : r+0|facade-nord). Permet à un plan "
             "réimporté de compléter cette façade au lieu d'en créer une seconde.")

    # =========================
    # GÉOMÉTRIE
    # =========================
    width = fields.Float("Largeur (m)")
    height = fields.Float("Hauteur (m)")
    min_x = fields.Float("X min", digits=(16, 3))
    min_y = fields.Float("Y min", digits=(16, 3))
    max_x = fields.Float("X max", digits=(16, 3))
    max_y = fields.Float("Y max", digits=(16, 3))
    layer = fields.Char("Calque du contour", index=True)

    gross_area = fields.Float(
        "Surface brute (m²)", compute="_compute_areas", store=True,
        help="Largeur × hauteur, ouvertures comprises.")
    opening_area = fields.Float(
        "Surface des ouvertures (m²)", compute="_compute_areas", store=True)
    net_area = fields.Float(
        "Surface pleine (m²)", compute="_compute_areas", store=True,
        help="Surface brute moins les ouvertures : c'est elle qui sert aux "
             "métrés d'enduit, de peinture ou de bardage.")
    opening_ratio = fields.Float(
        "Taux d'ouverture (%)", compute="_compute_areas", store=True, digits=(5, 2))

    # =========================
    # MURS (modèle existant)
    # =========================
    wall_ids = fields.One2many("construction.wall", "facade_id", string="Murs")
    wall_count = fields.Integer(compute="_compute_counts")
    material = fields.Selection(
        MATERIALS, string="Matériau principal", default="unknown",
        help="Matériau le plus cité par les annotations de cette façade.")
    wall_thickness = fields.Float(
        "Épaisseur des murs (m)",
        help="Non observable sur une façade : renseignée par une vue en plan "
             "ou en coupe du même niveau.")

    # =========================
    # CONTENU RELEVÉ
    # =========================
    level_ids = fields.One2many(
        "construction.facade.level", "facade_id", string="Niveaux")
    opening_ids = fields.One2many(
        "construction.facade.opening", "facade_id", string="Ouvertures")
    feature_ids = fields.One2many(
        "construction.facade.feature", "facade_id", string="Éléments architecturaux")
    dimension_ids = fields.One2many(
        "construction.facade.dimension", "facade_id", string="Cotes")
    annotation_ids = fields.One2many(
        "construction.facade.annotation", "facade_id", string="Annotations")

    level_count = fields.Integer(compute="_compute_counts")
    opening_count = fields.Integer(compute="_compute_counts")
    window_count = fields.Integer(compute="_compute_counts")
    door_count = fields.Integer(compute="_compute_counts")
    feature_count = fields.Integer(compute="_compute_counts")
    dimension_count = fields.Integer(compute="_compute_counts")
    annotation_count = fields.Integer(compute="_compute_counts")

    # =========================
    # ANALYSE / VALIDATION
    # =========================
    confidence = fields.Float(
        "Confiance (%)", digits=(5, 2),
        help="Niveau de confiance de la détection, entre 0 et 100.")
    detection_method = fields.Selection([
        ("layer", "Calque"),
        ("geometry", "Géométrie"),
        ("combined", "Calque + Géométrie"),
        ("manual", "Saisie manuelle"),
    ], string="Méthode de détection", default="geometry")
    is_validated = fields.Boolean("Validée", default=False, copy=False)
    notes = fields.Text("Remarques")

    _sql_constraints = [
        ("width_positive", "CHECK(width >= 0)",
         "La largeur de la façade doit être positive ou nulle."),
        ("height_positive", "CHECK(height >= 0)",
         "La hauteur de la façade doit être positive ou nulle."),
    ]

    @api.constrains("confidence")
    def _check_confidence(self):
        for facade in self:
            if facade.confidence and not 0 <= facade.confidence <= 100:
                raise ValidationError(
                    _("Le niveau de confiance doit être compris entre 0 et 100."))

    @api.depends("width", "height", "opening_ids.total_area")
    def _compute_areas(self):
        for facade in self:
            gross = facade.width * facade.height
            openings = sum(facade.opening_ids.mapped("total_area"))
            facade.gross_area = gross
            facade.opening_area = openings
            facade.net_area = max(gross - openings, 0.0)
            facade.opening_ratio = (openings / gross * 100.0) if gross else 0.0

    @api.depends("wall_ids", "level_ids", "opening_ids", "opening_ids.opening_type",
                 "feature_ids", "dimension_ids", "annotation_ids")
    def _compute_counts(self):
        for facade in self:
            facade.wall_count = len(facade.wall_ids)
            facade.level_count = len(facade.level_ids)
            facade.opening_count = len(facade.opening_ids)
            facade.window_count = len(facade.opening_ids.filtered(
                lambda o: o.opening_type in ("window", "french_window", "bay")))
            facade.door_count = len(facade.opening_ids.filtered(
                lambda o: o.opening_type in ("door", "garage_door")))
            facade.feature_count = len(facade.feature_ids)
            facade.dimension_count = len(facade.dimension_ids)
            facade.annotation_count = len(facade.annotation_ids)

    def action_validate(self):
        """Valider une façade, c'est arrêter les hauteurs d'étage qu'elle
        donne : elles deviennent la référence du niveau et complètent tous les
        murs de ce niveau qui n'en avaient pas encore — extérieurs de toute
        orientation et intérieurs, pas seulement le mur "titulaire" de la
        façade. Avant ce clic, aucune hauteur n'est propagée."""
        self.write({"is_validated": True})

        completed = self.env["construction.wall"]
        for project in self.project_id:
            completed |= self._fill_wall_heights(project)

        # Les murs complétés ont maintenant des métrés calculables : on repasse
        # par le circuit de validation des éléments, qui ne réécrit jamais un
        # brouillon déjà validé.
        for dwg in completed.dwg_file_id:
            dwg._enqueue_analysis_wall_elements()

        if completed:
            message = _("%s mur(s) ont reçu leur hauteur d'étage.") % len(completed)
        else:
            message = _("Aucun mur n'attendait de hauteur pour ces niveaux.")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Façade validée"),
                "message": message,
                "sticky": False,
                "type": "success",
            },
        }

    def action_reset(self):
        self.write({"is_validated": False})

    # =========================
    # HAUTEUR D'ÉTAGE : DE LA FAÇADE VERS LES MURS
    # =========================
    @api.model
    def _known_level_heights(self, project):
        """Hauteur d'étage connue pour chaque niveau du projet.

        Seule une façade VALIDÉE fait autorité : une hauteur issue d'une
        détection non relue ne doit pas se propager silencieusement aux murs
        de tous les autres plans. C'est le clic sur « Valider » qui déclenche
        le remplissage (cf. `action_validate`)."""
        heights = {}
        bands = self.env["construction.facade.level"].search([
            ("facade_id.project_id", "=", project.id),
            ("facade_id.is_validated", "=", True),
            ("level_id", "!=", False),
            ("height", ">", 0),
        ])
        for band in bands:
            known = heights.get(band.level_id.id)
            if known is None:
                heights[band.level_id.id] = band.height
            elif abs(known - band.height) > LEVEL_HEIGHT_TOLERANCE:
                _logger.warning(
                    "Projet %s, niveau %s : deux façades donnent des hauteurs "
                    "différentes (%.2f m retenue, %.2f m écartée sur « %s »). "
                    "Validez la bonne façade pour trancher.",
                    project.display_name, band.level_id.display_name,
                    known, band.height, band.facade_id.name)
        return heights

    @api.model
    def _fill_wall_heights(self, project):
        """Complète la hauteur de TOUS les murs du projet restés sans hauteur
        pour un niveau connu — extérieurs de toute orientation et intérieurs,
        pas seulement le mur « titulaire » de la façade (celui qui porte le
        nom « Mur façade Nord ») : c'est le seul qui reçoit sa hauteur par
        rapprochement direct de clé pendant la détection elle-même, tous les
        autres murs du même niveau dépendent de ce complément.

        Une vue en plan ne montre pas la hauteur des murs : elle reste vide
        jusqu'à ce qu'une façade du même niveau la donne. On ne remplit que le
        vide — une hauteur déjà relevée n'est jamais écrasée."""
        heights = self._known_level_heights(project)
        if not heights:
            return self.env["construction.wall"]

        walls = self.env["construction.wall"].search([
            ("project_id", "=", project.id),
            ("level_id", "in", list(heights)),
            "|", ("height", "=", False), ("height", "=", 0.0),
        ])
        for wall in walls:
            wall.height = heights[wall.level_id.id]

        if walls:
            _logger.info("Projet %s : hauteur d'étage posée sur %d mur(s)",
                         project.display_name, len(walls))
        return walls

    def action_view_walls(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Murs de la façade"),
            "res_model": "construction.wall",
            "view_mode": "tree,form",
            "domain": [("facade_id", "=", self.id)],
            "context": {"default_facade_id": self.id},
        }


class ConstructionFacadeLevel(models.Model):
    """Bande d'étage de la façade, entre deux dalles de plancher.

    Le niveau du projet (`level_id`) est résolu par l'appelant : le service ne
    connaît que le rang de la bande dans la façade (0 = la plus basse)."""

    _name = "construction.facade.level"
    _description = "Niveau d'une façade"
    _order = "facade_id, sequence, floor_index"

    facade_id = fields.Many2one(
        "construction.facade", string="Façade",
        required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(
        "project.project", related="facade_id.project_id", store=True, readonly=True)
    level_id = fields.Many2one(
        "construction.plan.level", string="Niveau du projet", index=True)
    name = fields.Char("Nom")
    sequence = fields.Integer("Séquence", default=10)
    floor_index = fields.Integer(
        "Rang dans la façade",
        help="0 pour la bande la plus basse du dessin, 1 pour la suivante...")

    bottom_elevation = fields.Float(
        "Altitude bas (m)", help="Mesurée depuis le bas de la façade.")
    top_elevation = fields.Float(
        "Altitude haut (m)", help="Mesurée depuis le bas de la façade.")
    height = fields.Float("Hauteur (m)", compute="_compute_height", store=True)
    slab_thickness = fields.Float(
        "Épaisseur de la dalle (m)",
        help="Dalle qui sépare ce niveau du suivant, quand elle est dessinée.")

    opening_ids = fields.One2many(
        "construction.facade.opening", "facade_level_id", string="Ouvertures")
    feature_ids = fields.One2many(
        "construction.facade.feature", "facade_level_id",
        string="Éléments architecturaux")

    _sql_constraints = [
        ("floor_index_uniq", "unique(facade_id, floor_index)",
         "Ce rang d'étage existe déjà sur cette façade."),
    ]

    @api.depends("bottom_elevation", "top_elevation")
    def _compute_height(self):
        for level in self:
            level.height = level.top_elevation - level.bottom_elevation

    @api.depends("name", "level_id", "floor_index")
    def _compute_display_name(self):
        for level in self:
            level.display_name = (
                level.name or level.level_id.name or _("Étage %s") % level.floor_index)


class ConstructionFacadeOpening(models.Model):
    """Porte, fenêtre ou baie relevée sur la façade.

    L'allège et le linteau sont les deux hauteurs qui commandent la pose :
    elles sont comptées depuis le bas de la façade, pas depuis le zéro du
    dessin."""

    _name = "construction.facade.opening"
    _description = "Ouverture d'une façade"
    _order = "facade_id, pos_x, pos_y"

    facade_id = fields.Many2one(
        "construction.facade", string="Façade",
        required=True, ondelete="cascade", index=True)
    facade_level_id = fields.Many2one(
        "construction.facade.level", string="Niveau de la façade",
        ondelete="set null", index=True)
    project_id = fields.Many2one(
        "project.project", related="facade_id.project_id", store=True, readonly=True)
    level_id = fields.Many2one(
        "construction.plan.level", related="facade_level_id.level_id",
        string="Niveau du projet", store=True, readonly=True)

    name = fields.Char("Désignation", required=True, default="Ouverture")
    mark = fields.Char(
        "Repère", index=True,
        help="Repère porté au dessin (F1, P2...). Vide si le plan n'en donne pas.")
    opening_type = fields.Selection([
        ("window", "Fenêtre"),
        ("french_window", "Porte-fenêtre"),
        ("door", "Porte"),
        ("garage_door", "Porte de garage"),
        ("bay", "Baie"),
        ("vent", "Ouverture technique"),
        ("unknown", "Inconnue"),
    ], string="Type", default="unknown", required=True, index=True)

    width = fields.Float("Largeur (m)")
    height = fields.Float("Hauteur (m)")
    sill_height = fields.Float(
        "Allège / façade (m)",
        help="Hauteur du bas de l'ouverture au-dessus du BAS DE LA FAÇADE. "
             "C'est la mesure relevée au dessin.")
    lintel_height = fields.Float(
        "Linteau / façade (m)",
        help="Hauteur du haut de l'ouverture au-dessus du bas de la façade.")
    sill_above_floor = fields.Float(
        "Allège (m)", compute="_compute_heights_above_floor", store=True,
        help="Hauteur d'allège au-dessus du sol de son niveau : c'est la cote "
             "de pose utilisée sur le chantier.")
    lintel_above_floor = fields.Float(
        "Hauteur sous linteau (m)", compute="_compute_heights_above_floor", store=True)
    quantity = fields.Integer(
        "Quantité", default=1,
        help="Nombre d'ouvertures identiques regroupées sur cette ligne.")
    area = fields.Float("Surface (m²)", compute="_compute_area", store=True)
    total_area = fields.Float(
        "Surface totale (m²)", compute="_compute_area", store=True)

    material = fields.Selection(MATERIALS, string="Menuiserie", default="unknown")
    layer = fields.Char("Calque", index=True)
    pos_x = fields.Float("X", digits=(16, 3))
    pos_y = fields.Float("Y", digits=(16, 3))
    center_x = fields.Float("Centre X", digits=(16, 3))
    center_y = fields.Float("Centre Y", digits=(16, 3))
    confidence = fields.Float("Confiance (%)", digits=(5, 2))
    notes = fields.Text("Remarques")

    _sql_constraints = [
        ("quantity_positive", "CHECK(quantity > 0)",
         "La quantité doit être strictement positive."),
    ]

    @api.depends("width", "height", "quantity")
    def _compute_area(self):
        for opening in self:
            opening.area = opening.width * opening.height
            opening.total_area = opening.area * (opening.quantity or 1)

    @api.depends("sill_height", "lintel_height", "facade_level_id.bottom_elevation")
    def _compute_heights_above_floor(self):
        """Une ouverture non rattachée à un niveau garde la cote relevée : à
        défaut de plancher connu, c'est la seule référence disponible."""
        for opening in self:
            floor = opening.facade_level_id.bottom_elevation
            opening.sill_above_floor = opening.sill_height - floor
            opening.lintel_above_floor = opening.lintel_height - floor

    @api.constrains("facade_id", "facade_level_id")
    def _check_level_belongs_to_facade(self):
        for opening in self:
            if (opening.facade_level_id
                    and opening.facade_level_id.facade_id != opening.facade_id):
                raise ValidationError(
                    _("Le niveau « %s » n'appartient pas à cette façade.")
                    % opening.facade_level_id.display_name)


class ConstructionFacadeFeature(models.Model):
    """Ouvrage architectural visible en façade : il ne porte pas le bâtiment
    mais se chiffre et se planifie (balcon, garde-corps, corniche, toiture)."""

    _name = "construction.facade.feature"
    _description = "Élément architectural d'une façade"
    _order = "facade_id, feature_type, pos_x"

    facade_id = fields.Many2one(
        "construction.facade", string="Façade",
        required=True, ondelete="cascade", index=True)
    facade_level_id = fields.Many2one(
        "construction.facade.level", string="Niveau de la façade",
        ondelete="set null", index=True)
    project_id = fields.Many2one(
        "project.project", related="facade_id.project_id", store=True, readonly=True)

    name = fields.Char("Désignation", required=True, default="Élément")
    mark = fields.Char("Repère")
    feature_type = fields.Selection([
        ("balcony", "Balcon"),
        ("terrace", "Terrasse"),
        ("railing", "Garde-corps"),
        ("cornice", "Corniche"),
        ("roof", "Toiture"),
        ("canopy", "Auvent"),
        ("stairs", "Escalier"),
        ("shutter", "Volet"),
        ("other", "Autre"),
    ], string="Type", default="other", required=True, index=True)

    width = fields.Float("Largeur (m)")
    height = fields.Float("Hauteur (m)")
    projection = fields.Float(
        "Saillie (m)",
        help="Débord hors du nu du mur. Non observable en façade : à compléter "
             "depuis une vue en plan ou en coupe.")
    quantity = fields.Integer("Quantité", default=1)
    area = fields.Float("Surface (m²)", compute="_compute_area", store=True)

    material = fields.Selection(MATERIALS, string="Matériau", default="unknown")
    layer = fields.Char("Calque", index=True)
    pos_x = fields.Float("X", digits=(16, 3))
    pos_y = fields.Float("Y", digits=(16, 3))
    center_x = fields.Float("Centre X", digits=(16, 3))
    center_y = fields.Float("Centre Y", digits=(16, 3))
    confidence = fields.Float("Confiance (%)", digits=(5, 2))
    notes = fields.Text("Remarques")

    @api.depends("width", "height", "quantity")
    def _compute_area(self):
        for feature in self:
            feature.area = feature.width * feature.height * (feature.quantity or 1)


class ConstructionFacadeDimension(models.Model):
    """Cote portée au dessin.

    Deux origines très différentes : une entité DIMENSION, qui porte sa mesure
    et se lit sans ambiguïté, ou un simple texte (« +3.00 ») quand le
    dessinateur a coté à la main."""

    _name = "construction.facade.dimension"
    _description = "Cote d'une façade"
    _order = "facade_id, dimension_type, pos_x"

    facade_id = fields.Many2one(
        "construction.facade", string="Façade",
        required=True, ondelete="cascade", index=True)
    project_id = fields.Many2one(
        "project.project", related="facade_id.project_id", store=True, readonly=True)

    name = fields.Char("Libellé", required=True, default="Cote")
    dimension_type = fields.Selection([
        ("horizontal", "Cote horizontale"),
        ("vertical", "Cote verticale"),
        ("altimetric", "Niveau altimétrique"),
        ("other", "Autre"),
    ], string="Type", default="other", required=True, index=True)

    value = fields.Float("Mesure (m)")
    elevation = fields.Float(
        "Altitude (m)", help="Renseignée pour les niveaux altimétriques (+3.00, ±0.00).")
    text = fields.Char("Texte du dessin")
    origin = fields.Selection([
        ("dimension", "Entité de cotation"),
        ("text", "Texte relevé"),
        ("manual", "Saisie manuelle"),
    ], string="Origine", default="dimension")

    layer = fields.Char("Calque", index=True)
    pos_x = fields.Float("X", digits=(16, 3))
    pos_y = fields.Float("Y", digits=(16, 3))


class ConstructionFacadeAnnotation(models.Model):
    """Texte du dessin, rattaché à la façade qu'il concerne et classé par ce
    qu'il apporte.

    À ne pas confondre avec construction.dwg.annotation, qui est le relevé
    brut de TOUS les textes du fichier : ici le texte est interprété (repère,
    matériau, altitude, détail technique) et rattaché à une façade."""

    _name = "construction.facade.annotation"
    _description = "Annotation d'une façade"
    _order = "facade_id, annotation_type, pos_y desc"

    facade_id = fields.Many2one(
        "construction.facade", string="Façade",
        required=True, ondelete="cascade", index=True)
    facade_level_id = fields.Many2one(
        "construction.facade.level", string="Niveau de la façade",
        ondelete="set null")
    project_id = fields.Many2one(
        "project.project", related="facade_id.project_id", store=True, readonly=True)

    name = fields.Char("Intitulé", required=True, default="Annotation")
    text = fields.Text("Texte", required=True)
    annotation_type = fields.Selection([
        ("mark", "Repère"),
        ("material", "Matériau"),
        ("level", "Niveau altimétrique"),
        ("technical", "Détail technique"),
        ("general", "Texte"),
    ], string="Nature", default="general", required=True, index=True)
    material = fields.Selection(MATERIALS, string="Matériau cité")

    layer = fields.Char("Calque", index=True)
    pos_x = fields.Float("X", digits=(16, 3))
    pos_y = fields.Float("Y", digits=(16, 3))
