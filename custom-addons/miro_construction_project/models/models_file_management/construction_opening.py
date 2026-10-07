import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Champs de l'ouverture qui alimentent les cotes et métrés de son élément.
SYNC_FIELDS = {"width", "thickness", "height", "sill_height", "opening_type"}
# Champs qui changent la surface déduite du mur porteur, ou son dessin.
WALL_SYNC_FIELDS = {"width", "height", "sill_height", "opening_type", "wall_id",
                    "center_x", "center_y", "active"}

# Hauteur et allège dessinées pour une ouverture dont la hauteur n'est pas
# encore connue (schéma seulement, jamais déduites du mur).
DRAWING_DEFAULTS = {"door": (0.0, 2.10), "garage_door": (0.0, 2.10),
                    "french_window": (0.0, 2.15), "window": (0.90, 1.25),
                    "bay": (0.0, 2.10)}


class ConstructionOpening(models.Model):
    """Porte, fenêtre ou baie détectée, complétée d'un plan à l'autre.

    Comme un mur, une ouverture n'est jamais entièrement visible sur un seul
    plan : la vue en plan donne sa largeur et l'épaisseur du mur qu'elle
    traverse, la façade sa hauteur et son allège. Chaque import du même
    niveau complète ce qui manque, sans écraser ce qui est déjà connu
    (cf. service/opening_detection_service.merge_detected_openings).

    À ne pas confondre avec construction.facade.opening, qui est le relevé
    brut d'UNE façade : ici l'ouverture est consolidée toutes vues
    confondues, et c'est elle qui passe par le circuit de validation
    (brouillon -> élément de construction -> phases)."""

    _name = "construction.opening"
    _description = "Ouverture détectée (porte, fenêtre)"
    _order = "project_id, level_id, orientation, facade_offset, id"

    # =========================
    # IDENTIFICATION
    # =========================
    name = fields.Char("Nom", required=True, default="Nouvelle ouverture")
    active = fields.Boolean("Actif", default=True)
    dwg_file_id = fields.Many2one(
        "construction.dwg.files", string="Plan d'origine",
        required=True, ondelete="cascade", index=True,
        help="Plan qui a fait apparaître cette ouverture pour la première fois.")
    project_id = fields.Many2one(
        "project.project", string="Projet", related="dwg_file_id.project_id",
        store=True, index=True, readonly=True)
    level_id = fields.Many2one("construction.plan.level", string="Niveau", index=True)
    wall_id = fields.Many2one(
        "construction.wall", string="Mur porteur de l'ouverture",
        ondelete="set null", index=True,
        help="Mur dans lequel l'ouverture est percée. Donne son épaisseur à "
             "l'ouverture tant qu'aucune vue en plan ne l'a mesurée.")
    match_key = fields.Char(
        "Clé d'identification", index=True, copy=False,
        help="Identité de l'ouverture dans le niveau (ex. : r+0|ouv-sud-1.70 = "
             "façade sud, centrée à 1,70 m du bord gauche vu de l'extérieur). "
             "Permet à un plan d'une autre vue de compléter cette ouverture "
             "au lieu d'en créer une seconde.")
    source_file_ids = fields.Many2many(
        "construction.dwg.files", "construction_opening_source_file_rel",
        "opening_id", "dwg_file_id", string="Plans sources",
        help="Tous les plans qui ont renseigné une partie de cette ouverture.")
    source_view_ids = fields.Many2many(
        "construction.plan.view", "construction_opening_source_view_rel",
        "opening_id", "plan_view_id", string="Vues sources",
        help="Types de vue ayant permis d'observer cette ouverture.")

    # =========================
    # CLASSIFICATION
    # =========================
    opening_type = fields.Selection([
        ("window", "Fenêtre"),
        ("french_window", "Porte-fenêtre"),
        ("door", "Porte"),
        ("garage_door", "Porte de garage"),
        ("bay", "Baie"),
        ("vent", "Ouverture technique"),
        ("unknown", "Inconnue"),
    ], string="Nature", default="unknown", required=True, index=True,
        help="Une vue en plan ne distingue pas toujours une fenêtre d'une "
             "porte-fenêtre : la façade la précise.")
    wall_position = fields.Selection([
        ("exterior", "Extérieure"),
        ("interior", "Intérieure"),
        ("unknown", "Inconnue"),
    ], string="Position", default="unknown", required=True)
    orientation = fields.Selection([
        ("nord", "Nord"),
        ("sud", "Sud"),
        ("est", "Est"),
        ("ouest", "Ouest"),
    ], string="Façade",
        help="Façade sur laquelle donne l'ouverture. Avec la position le long "
             "de la façade, c'est ce qui rapproche l'ouverture vue en plan de "
             "la même vue en façade.")
    facade_offset = fields.Float(
        "Position sur la façade (m)", digits=(16, 3),
        help="Distance du centre de l'ouverture au bord gauche de sa façade, "
             "façade vue de l'extérieur.")
    mark = fields.Char("Repère", help="Repère porté au dessin (F1, P2...).")
    layer = fields.Char("Calque", index=True)

    # =========================
    # GÉOMÉTRIE (vue en plan)
    # =========================
    start_x = fields.Float("Début X")
    start_y = fields.Float("Début Y")
    end_x = fields.Float("Fin X")
    end_y = fields.Float("Fin Y")
    center_x = fields.Float("Centre X")
    center_y = fields.Float("Centre Y")

    # =========================
    # DIMENSIONS
    # =========================
    width = fields.Float(
        "Largeur (m)", help="Longueur prise dans le mur. Vue en plan et en façade.")
    thickness = fields.Float(
        "Épaisseur (m)",
        help="Épaisseur du mur traversé (profondeur du tableau). Vue en plan "
             "uniquement, ou reprise du mur porteur.")
    height = fields.Float("Hauteur (m)", help="Vue en façade uniquement.")
    sill_height = fields.Float(
        "Allège (m)", help="Hauteur du bas de l'ouverture au-dessus du sol "
                           "de son niveau. Vue en façade uniquement.")
    lintel_height = fields.Float(
        "Hauteur sous linteau (m)", help="Au-dessus du sol de son niveau.")

    area = fields.Float("Surface (m²)", compute="_compute_area", store=True)

    # =========================
    # ANALYSE
    # =========================
    confidence = fields.Float(
        "Confiance (%)", digits=(5, 2),
        help="Niveau de confiance de la détection entre 0 et 100")
    detection_method = fields.Selection([
        ("layer", "Calque"),
        ("geometry", "Géométrie"),
        ("combined", "Plusieurs vues"),
    ], string="Méthode de détection", default="layer")
    is_complete = fields.Boolean(
        "Complète", compute="_compute_is_complete", store=True,
        help="Largeur, épaisseur et hauteur connues : l'ouverture peut être "
             "chiffrée.")

    # =========================
    # ÉLÉMENT DE CONSTRUCTION
    # =========================
    element_ids = fields.One2many(
        "construction.element", "opening_id", string="Éléments de construction")
    draft_ids = fields.One2many(
        "construction.element.draft", "opening_id", string="Brouillons d'éléments")
    element_id = fields.Many2one(
        "construction.element", string="Élément de construction",
        compute="_compute_element_id",
        help="Ouvrage validé qui représente cette ouverture. Vide tant que "
             "son brouillon n'a pas été validé puis généré.")

    _sql_constraints = [
        ("width_positive", "CHECK(width >= 0)",
         "La largeur de l'ouverture doit être positive ou nulle."),
        ("thickness_positive", "CHECK(thickness >= 0)",
         "L'épaisseur de l'ouverture doit être positive ou nulle."),
        ("height_positive", "CHECK(height >= 0)",
         "La hauteur de l'ouverture doit être positive ou nulle."),
    ]

    @api.constrains("confidence")
    def _check_confidence(self):
        for opening in self:
            if opening.confidence and not 0 <= opening.confidence <= 100:
                raise ValidationError(
                    _("Le niveau de confiance doit être compris entre 0 et 100."))

    @api.depends("width", "height")
    def _compute_area(self):
        for opening in self:
            opening.area = opening.width * opening.height

    @api.depends("width", "thickness", "height")
    def _compute_is_complete(self):
        for opening in self:
            opening.is_complete = bool(
                opening.width and opening.thickness and opening.height)

    @api.depends("element_ids")
    def _compute_element_id(self):
        for opening in self:
            opening.element_id = opening.element_ids[:1]

    # =========================
    # SYNCHRONISATION OUVERTURE -> ÉLÉMENT
    # =========================
    @api.model_create_multi
    def create(self, vals_list):
        openings = super().create(vals_list)
        openings.wall_id._sync_elements()
        return openings

    def write(self, vals):
        old_walls = self.wall_id if "wall_id" in vals else self.env["construction.wall"]
        res = super().write(vals)
        if SYNC_FIELDS & set(vals):
            self._sync_elements()
        if WALL_SYNC_FIELDS & set(vals):
            # La surface déduite du mur change : son brouillon, son élément
            # et l'ancien mur porteur sont recalculés.
            (old_walls | self.wall_id)._sync_elements()
        return res

    def unlink(self):
        walls = self.wall_id
        res = super().unlink()
        walls.exists()._sync_elements()
        return res

    def _sync_elements(self):
        """Reporte cotes et métrés sur les brouillons non encore générés et
        sur les éléments, par le même calcul que l'analyse
        (`_opening_to_item`) : un élément synchronisé est identique à celui
        qu'une nouvelle analyse aurait produit."""
        Analysis = self.env["construction.analysis"]
        for opening in self:
            if not (opening.element_ids or opening.draft_ids):
                continue
            item = Analysis._opening_to_item(opening)
            etype = self.env["construction.element.type"].search(
                [("code", "=", item["type"])], limit=1)

            for draft in opening.draft_ids.filtered(
                    lambda d: d.state in ("pending", "validated")):
                dims = dict(draft.dimensions or {})
                dims.update(item["dimensions"])
                quantities = dict(draft.quantities or {})
                quantities.update(item["quantities"])
                vals = {
                    "dimensions": dims,
                    "quantities": quantities,
                    "issue": item["issue"],
                    "confidence": item["confidence"],
                }
                # Une façade peut révéler qu'une « fenêtre » vue en plan est
                # une porte-fenêtre : le brouillon change alors de type.
                if draft.state == "pending" and etype and draft.type_id != etype:
                    vals.update(type_code=item["type"], type_id=etype.id)
                draft.write(vals)

            opening.element_ids._apply_wall_measures(item)

    @api.model
    def _link_elements(self, openings=None):
        """Relie les brouillons et éléments à leur ouverture par leur clé
        (OUV-...). Une relance de détection recrée les ouvertures que le plan
        était seul à connaître : sans ce lien, leurs éléments déjà générés
        resteraient orphelins."""
        Analysis = self.env["construction.analysis"]
        Draft = self.env["construction.element.draft"]
        Element = self.env["construction.element"].with_context(active_test=False)
        openings = openings if openings is not None else self.search([])

        for opening in openings:
            key = Analysis._opening_key(opening)
            files = opening.dwg_file_id | opening.source_file_ids
            Draft.search([
                ("opening_id", "=", False),
                ("key", "=", key),
                ("level_id", "=", opening.level_id.id),
                ("analysis_id.file_id", "in", files.ids),
            ]).write({"opening_id": opening.id})
            if opening.project_id:
                Element.search([
                    ("opening_id", "=", False),
                    ("key", "=", key),
                    ("level_id", "=", opening.level_id.id),
                    ("project_id", "=", opening.project_id.id),
                ]).write({"opening_id": opening.id})

    # =========================
    # MUR PORTEUR
    # =========================
    # Distance max entre le centre de l'ouverture et l'axe de son mur (m),
    # au-delà de la demi-épaisseur du mur.
    _HOST_WALL_TOLERANCE = 0.30

    @api.model
    def _link_host_walls(self, project):
        """Rattache chaque ouverture du projet au mur qui la porte, puis lui
        donne l'épaisseur de ce mur si aucune vue en plan ne l'a mesurée.

        - vue en plan : le mur du même niveau dont l'axe passe au plus près
          du centre de l'ouverture ;
        - façade seule (pas de position en plan) : le mur de façade de même
          orientation et de même niveau (clé « facade-<orientation> »).

        Rejoué après chaque détection de murs ou d'ouvertures : l'ordre
        d'import des plans est libre."""
        if not project:
            return self.browse()
        Wall = self.env["construction.wall"]
        openings = self.search([("project_id", "=", project.id)])
        walls = Wall.search([("project_id", "=", project.id)])
        by_level = {}
        for wall in walls:
            by_level.setdefault(wall.level_id.id, Wall)
            by_level[wall.level_id.id] |= wall

        completed = self.browse()
        for opening in openings:
            candidates = by_level.get(opening.level_id.id, Wall)
            wall = (opening._nearest_wall(candidates) if opening._has_axis()
                    else opening._facade_wall(candidates))
            vals = {}
            if wall and wall != opening.wall_id:
                vals["wall_id"] = wall.id
            host = wall or opening.wall_id
            if host.thickness and not opening.thickness:
                vals["thickness"] = host.thickness
                completed |= opening
            if vals:
                opening.write(vals)
        return completed

    def _has_axis(self):
        self.ensure_one()
        return (self.start_x, self.start_y) != (self.end_x, self.end_y)

    def _nearest_wall(self, walls):
        """Mur dont l'axe passe au plus près du centre de l'ouverture, à moins
        de sa demi-épaisseur + tolérance. Le centre d'une ouverture tombe dans
        le prolongement du mur, pas sur l'un de ses morceaux : on mesure donc
        à la droite qui porte l'axe, bornée à l'étendue du mur."""
        self.ensure_one()
        best, best_distance = None, None
        for wall in walls:
            if (wall.start_x, wall.start_y) == (wall.end_x, wall.end_y):
                continue
            distance = self._distance_to_wall_line(wall)
            if distance is None:
                continue
            limit = (wall.thickness or 0.0) / 2.0 + self._HOST_WALL_TOLERANCE
            if distance <= limit and (best_distance is None or distance < best_distance):
                best, best_distance = wall, distance
        return best

    def _distance_to_wall_line(self, wall):
        """Écart perpendiculaire du centre à l'axe du mur, si l'ouverture est
        parallèle au mur et tombe dans son étendue (± sa propre largeur :
        une baie interrompt le mur, elle n'est jamais sur ses morceaux)."""
        dx, dy = wall.end_x - wall.start_x, wall.end_y - wall.start_y
        length = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / length, dy / length
        ox, oy = self.end_x - self.start_x, self.end_y - self.start_y
        olength = (ox * ox + oy * oy) ** 0.5 or 1.0
        if abs(ox / olength * ux + oy / olength * uy) < 0.98:   # ~11°
            return None
        px, py = self.center_x - wall.start_x, self.center_y - wall.start_y
        along = px * ux + py * uy
        margin = self.width or 0.0
        if not -margin <= along <= length + margin:
            return None
        return abs(px * -uy + py * ux)

    def _facade_wall(self, walls):
        self.ensure_one()
        if not self.orientation:
            return None
        suffix = "|facade-%s" % self.orientation
        return walls.filtered(
            lambda w: (w.match_key or "").endswith(suffix))[:1] or None

    # =========================
    # ACTIONS
    # =========================
    def action_open_element(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Élément de construction"),
            "res_model": "construction.element",
            "res_id": self.element_id.id,
            "view_mode": "form",
        }


class ConstructionWall(models.Model):
    _inherit = "construction.wall"

    opening_ids = fields.One2many(
        "construction.opening", "wall_id", string="Ouvertures")
    opening_count = fields.Integer(compute="_compute_opening_stats")
    opening_area = fields.Float(
        "Surface des ouvertures (m²)", compute="_compute_opening_stats",
        help="Surface des portes et fenêtres percées dans ce mur.")
    openings_without_height = fields.Integer(
        "Ouvertures sans hauteur", compute="_compute_opening_stats",
        help="Leur surface n'est pas encore déduite du mur.")
    net_area = fields.Float(
        "Surface nette (m²)", compute="_compute_opening_stats",
        help="Surface du mur moins celle de ses ouvertures : c'est elle qui "
             "chiffre le mur.")
    net_volume = fields.Float(
        "Volume net (m³)", compute="_compute_opening_stats")

    @api.depends("opening_ids", "opening_ids.area", "opening_ids.height",
                 "area", "thickness")
    def _compute_opening_stats(self):
        for wall in self:
            wall.opening_count = len(wall.opening_ids)
            wall.opening_area = sum(wall.opening_ids.mapped("area"))
            wall.openings_without_height = len(
                wall.opening_ids.filtered(lambda o: o.width and not o.height))
            wall.net_area = max((wall.area or 0.0) - wall.opening_area, 0.0)
            wall.net_volume = wall.net_area * (wall.thickness or 0.0)

    def _opening_layout(self):
        """Ouvertures du mur pour son schéma, le long de son axe :
        [{offset, width, sill, height, kind, label, known}], en mètres depuis
        le début du mur. Une hauteur inconnue est dessinée à une valeur de
        convention (`known` = False), jamais déduite."""
        self.ensure_one()
        dx, dy = self.end_x - self.start_x, self.end_y - self.start_y
        axis = (dx * dx + dy * dy) ** 0.5
        if not axis:
            return []
        ux, uy = dx / axis, dy / axis
        # Coordonnées du dessin -> mètres, par la longueur du mur
        factor = (self.length / axis) if self.length else 1.0
        layout = []
        for opening in self.opening_ids.filtered("width"):
            if not (opening.center_x or opening.center_y):
                continue
            along = ((opening.center_x - self.start_x) * ux
                     + (opening.center_y - self.start_y) * uy) * factor
            sill, height = DRAWING_DEFAULTS.get(opening.opening_type, (0.0, 2.10))
            layout.append({
                "offset": round(along - opening.width / 2.0, 3),
                "width": opening.width,
                "sill": opening.sill_height if opening.height else sill,
                "height": opening.height or height,
                "kind": opening.opening_type,
                "label": opening.mark or "",
                "known": bool(opening.height),
            })
        return sorted(layout, key=lambda o: o["offset"])

    def write(self, vals):
        res = super().write(vals)
        if "thickness" in vals:
            # L'épaisseur d'un mur enfin connue complète les ouvertures qu'il
            # porte et qu'aucune vue en plan n'a mesurées.
            for wall in self.filtered("thickness"):
                wall.opening_ids.filtered(lambda o: not o.thickness).write(
                    {"thickness": wall.thickness})
        return res

    def action_view_openings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Ouvertures du mur"),
            "res_model": "construction.opening",
            "view_mode": "tree,form",
            "domain": [("wall_id", "=", self.id)],
        }
