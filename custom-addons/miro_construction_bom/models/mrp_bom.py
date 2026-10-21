from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Unité dans laquelle chaque métré d'élément est exprimé. Une nomenclature
# rattachée à une phase doit avoir une unité de la même catégorie (volume,
# poids, surface) : c'est ce qui permet de convertir.
QTY_KEY_UOM = {
    'beton_m3': 'uom.product_uom_cubic_meter',
    'acier_kg': 'uom.product_uom_kgm',
    'coffrage_m2': 'uom.uom_square_meter',
    'surface_m2': 'uom.uom_square_meter',
}


class MrpBom(models.Model):
    """Nomenclature native utilisée comme RECETTE de chantier : les
    matériaux consommés pour une unité de l'ouvrage qu'elle « fabrique »
    (1 m³ de béton coulé, 1 kg d'acier posé, 1 m² coffré...).

    Aucun ordre de fabrication n'est créé : la recette sert au calcul des
    besoins matériaux des phases (cf. construction.material.need)."""
    _inherit = 'mrp.bom'

    # Pour etre proposer dans la gabarit de phase 
    construction_ok = fields.Boolean(
        "Recette de chantier",
        help="Proposée sur les phases des gabarits et des types d'éléments.")
    phase_line_ids = fields.One2many(
        'construction.phase.template.line', 'bom_id', string="Phases")
    need_ids = fields.One2many('construction.material.need', 'bom_id', string="Besoins")
    need_count = fields.Integer(compute='_compute_need_count')

    def _compute_need_count(self):
        data = self.env['construction.material.need']._read_group(
            [('bom_id', 'in', self.ids)], ['bom_id'], ['__count'])
        counts = {bom.id: count for bom, count in data}
        for bom in self:
            bom.need_count = counts.get(bom.id, 0)

    @api.model
    def _native_uom(self, qty_key):
        return self.env.ref(QTY_KEY_UOM[qty_key]) if qty_key in QTY_KEY_UOM else None

    @api.model
    def _check_unit_for(self, bom, qty_key, phase_name):
        native = self._native_uom(qty_key)
        if native and bom.product_uom_id.category_id != native.category_id:
            raise ValidationError(_(
                "La nomenclature « %(bom)s » est exprimée en %(unit)s : elle ne "
                "peut pas chiffrer la phase « %(phase)s », dont la quantité est "
                "en %(native)s.") % {'bom': bom.display_name, 'unit': bom.product_uom_id.name,
                                     'phase': phase_name, 'native': native.name})

    def _construction_explode(self, quantity):
        """Matériaux pour `quantity` (dans l'unité de la nomenclature) :
        liste de (ligne, quantité dans l'unité de la ligne).

        Comme `explode()` natif, descend dans les kits (nomenclatures de type
        « Kit » d'un composant, ex. le mortier d'une maçonnerie) et ignore les
        lignes réservées à d'autres variantes. Deux différences voulues :
        le coefficient de chaque ligne (pertes, réemploi) s'applique, et rien
        n'est arrondi à l'unité supérieure — sur un besoin par phase, l'arrondi
        natif gonflerait chaque parpaing ou kilo de ciment."""
        self.ensure_one()
        totals = {}

        def walk(bom, product, times):
            for line in bom.bom_line_ids:
                if line._skip_bom_line(product):
                    continue
                qty = times * line.product_qty * (line.coefficient or 1.0)
                kit = self._bom_find(line.product_id, bom_type='phantom').get(line.product_id)
                if kit and kit.product_qty:
                    walk(kit, line.product_id, line.product_uom_id._compute_quantity(
                        qty, kit.product_uom_id, round=False) / kit.product_qty)
                else:
                    totals[line] = totals.get(line, 0.0) + qty

        if self.product_qty:
            walk(self, self.product_id or self.product_tmpl_id.product_variant_id,
                 quantity / self.product_qty)
        return list(totals.items())

    def action_refresh_needs(self):
        """Recalcule les besoins des phases non commencées qui utilisent ces
        nomenclatures. Une phase commencée garde ses besoins : ils ont pu
        servir à commander."""
        tasks = self.env['construction.material.need'].search(
            [('bom_id', 'in', self.ids)]).task_id
        lines = self.phase_line_ids | self.env['construction.element.type.bom'].search(
            [('bom_id', 'in', self.ids)]).phase_line_id
        tasks |= self.env['project.task'].search([('phase_template_line_id', 'in', lines.ids)])
        refreshed = tasks._refresh_material_needs()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _("Besoins matériaux"), 'type': 'success', 'sticky': False,
                       'message': _("%d phase(s) recalculée(s).") % len(refreshed)},
        }

    def action_view_needs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Besoins — %s") % self.display_name,
            'res_model': 'construction.material.need', 'view_mode': 'tree,pivot,form',
            'domain': [('bom_id', '=', self.id)],
        }


class MrpBomLine(models.Model):
    """Une ligne vise un article Odoo réel ; sa catégorie de matériau dit
    quel besoin générique il couvre, pour qu'un projet puisse retenir un autre
    produit de la même catégorie (cf. construction.project.material)."""
    _inherit = 'mrp.bom.line'

    material_category_id = fields.Many2one(
        'construction.material.category', string="Besoin couvert",
        compute='_compute_material_category_id', store=True, readonly=False,
        help="Catégorie de matériau de l'article. Un projet peut y substituer "
             "tout produit de cette catégorie ou de ses sous-catégories.")
    coefficient = fields.Float(
        "Coefficient", default=1.0, digits=(16, 3),
        help="Pertes ou réemploi : 1,05 = 5 % de pertes ; 0,20 = panneau "
             "réemployé 5 fois.")
        
    @api.depends('product_id')
    def _compute_material_category_id(self):
        for line in self:
            if line.product_id.material_category_id:
                line.material_category_id = line.product_id.material_category_id

    @api.constrains('product_id', 'material_category_id')
    def _check_material_category(self):
        Category = self.env['construction.material.category']
        for line in self.filtered('material_category_id'):
            category = line.product_id.material_category_id
            if category and not Category.search_count([
                    ('id', '=', category.id), ('id', 'child_of', line.material_category_id.id)]):
                raise ValidationError(_(
                    "Le produit « %s » ne relève pas de la catégorie « %s ».")
                    % (line.product_id.display_name, line.material_category_id.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._link_products()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if 'product_id' in vals or 'material_category_id' in vals:
            self._link_products()
        return res

    def _link_products(self):
        """Un article sans catégorie de matériau prend celle de la ligne : il
        devient alors proposé pour ce besoin dans les projets."""
        for line in self.filtered(lambda l: l.material_category_id
                                  and not l.product_id.material_category_id):
            line.product_id.product_tmpl_id.material_category_id = line.material_category_id
