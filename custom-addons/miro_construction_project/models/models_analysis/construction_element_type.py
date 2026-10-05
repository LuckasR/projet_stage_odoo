from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Unités de mesure des caractéristiques d'un ouvrage. Le suffixe du code
# suffit rarement à les deviner (« l » est en mètres, « beton_m3 » en m³) :
# c'est la ligne de caractéristique qui porte l'unité, pas une convention
# de nommage.
UOM_SELECTION = [
    ('m', "m"),
    ('m2', "m²"),
    ('m3', "m³"),
    ('kg', "kg"),
    ('u', "u"),
]


class ConstructionElementType(models.Model):
    _name = 'construction.element.type'
    _description = "Type d'élément de construction"
    _order = 'name'

    name = fields.Char("Nom", required=True, translate=True)
    code = fields.Char(
        "Code d'analyse", required=True,
        help="Valeur du champ « type » renvoyée par l'analyse (ex. : semelle, poteau).")
    work_name = fields.Char(
        "Ouvrage de rattachement", required=True,
        help="Nom de la task Ouvrage sous laquelle les phases sont créées (ex. : Fondation). "
             "Elle est créée automatiquement dans le projet si elle n'existe pas.")
    phase_template_id = fields.Many2one(
        'construction.phase.template', string="Gabarit de phases")
    ouvrage_per_level = fields.Boolean(
        "Un ouvrage par niveau",
        help="Si coché, la task Ouvrage est créée par niveau (ex. : « Poteaux - RDC », "
             "« Poteaux - R+1 »). Sinon, un seul ouvrage pour tout le projet.")
    plan_type_ids = fields.Many2many(
        'construction.plan.type', 'construction_element_type_plan_type_rel',
        'element_type_id', 'plan_type_id', string="Types de plan concernés",
        help="Ce type d'élément n'est cherché que sur les plans de ces types "
             "(ex. : Semelle -> Plan de fondation). Vide = tous les plans.")

    # --- Paramètres du moteur d'analyse DXF -----------------------------
    dxf_block_keyword = fields.Char(
        "Mot-clé du bloc DXF",
        help="Un bloc dont le nom contient ce mot (insensible à la casse) est détecté "
             "comme un élément de ce type. Ex. : SEMELLE.")
    dxf_layer_keyword = fields.Char(
        "Mot-clé du calque DXF",
        help="Un bloc placé sur un calque dont le nom contient ce mot est détecté "
             "comme un élément de ce type. Ex. : FOND.")
    steel_ratio_kg_m3 = fields.Float(
        "Ratio d'acier (kg/m³)", default=0.0,
        help="Si le plan ne donne pas le poids d'acier, il est estimé : béton (m³) × ratio.")

    field_ids = fields.One2many(
        'construction.element.type.field', 'type_id',
        string="Caractéristiques attendues",
        help="Ce qu'il faut connaître d'un ouvrage de ce type pour pouvoir le "
             "chiffrer. Une caractéristique marquée obligatoire bloque la "
             "validation du brouillon tant qu'elle n'est pas renseignée.")

    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', "Ce code de type existe déjà."),
    ]


class ConstructionElementTypeField(models.Model):
    """Caractéristique attendue d'un ouvrage : ce qu'il faut en connaître, et
    dans quelle unité.

    Sans ces lignes, chaque type d'ouvrage supposerait implicitement les mêmes
    trois dimensions (L, l, h), ce qui est faux : une semelle filante se
    chiffre au mètre linéaire, un dallage au mètre carré, un poteau au mètre
    cube. Elles servent à deux choses :

      - compléter ce que le plan ne montre pas (`default_value`) : une vue en
        plan ne donne jamais la hauteur d'un ouvrage, alors que la
        nomenclature du projet la fixe une fois pour toutes ;
      - refuser la validation d'un brouillon incomplet (`required`), plutôt
        que de générer un élément dont les métrés seront faux.
    """

    _name = 'construction.element.type.field'
    _description = "Caractéristique d'un type d'élément"
    _order = 'type_id, sequence, id'

    type_id = fields.Many2one(
        'construction.element.type', string="Type d'élément",
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer("Séquence", default=10)
    name = fields.Char("Libellé", required=True, translate=True)
    code = fields.Char(
        "Clé", required=True,
        help="Clé technique dans les données de l'analyse : l, w, h, ep pour "
             "une dimension ; beton_m3, acier_kg, coffrage_m2, surface_m2 "
             "pour une quantité.")
    nature = fields.Selection([
        ('dimension', "Dimension"),
        ('quantity', "Quantité"),
    ], string="Nature", default='dimension', required=True,
        help="Une dimension est relevée sur le plan ou saisie ; une quantité "
             "est le métré qui en découle.")
    uom = fields.Selection(
        UOM_SELECTION, string="Unité", default='m', required=True)
    required = fields.Boolean(
        "Obligatoire", default=False,
        help="Empêche la validation du brouillon tant que la valeur est vide.")
    default_value = fields.Float(
        "Valeur par défaut",
        help="Appliquée par « Calculer les métrés » quand le plan n'a pas pu "
             "donner la valeur. Ex. : hauteur de semelle fixée par la "
             "nomenclature du projet.")

    _sql_constraints = [
        ('code_uniq', 'unique(type_id, code)',
         "Cette caractéristique existe déjà pour ce type d'élément."),
    ]

    @api.constrains('nature', 'code')
    def _check_quantity_code(self):
        """Une quantité doit porter une clé que le circuit des phases sait
        lire : les gabarits de phases chiffrent sur ces clés (`qty_key`)."""
        known = self.env['construction.element.draft']._QUANTITY_KEYS
        for line in self:
            if line.nature == 'quantity' and line.code not in known:
                raise ValidationError(_(
                    "La quantité « %s » utilise la clé « %s », inconnue du "
                    "circuit de métrés. Clés acceptées : %s.")
                    % (line.name, line.code, ', '.join(known)))

    @api.depends('name', 'uom')
    def _compute_display_name(self):
        labels = dict(UOM_SELECTION)
        for line in self:
            line.display_name = "%s (%s)" % (line.name, labels.get(line.uom, ''))

    # ------------------------------------------------------------------
    # Propagation vers les éléments existants
    # ------------------------------------------------------------------
    # Déclarer une caractéristique sur un type doit la faire apparaître sur
    # les ouvrages déjà créés : sans cela, il faudrait rouvrir chaque élément
    # pour que sa fiche se mette à jour.
    def _elements_of_type(self):
        return self.env['construction.element'].with_context(
            active_test=False).search([('element_type_id', 'in', self.type_id.ids)])

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._elements_of_type()._sync_value_lines()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'type_id' in vals:
            self._elements_of_type()._sync_value_lines()
        return res

    def unlink(self):
        elements = self._elements_of_type()
        res = super().unlink()
        elements._sync_value_lines()
        return res
