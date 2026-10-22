from odoo import _, api, fields, models
from odoo.tools import float_compare, float_is_zero

# Métrés d'un élément dont la modification recalcule les besoins
QTY_FIELDS = ('qty_beton_m3', 'qty_acier_kg', 'qty_coffrage_m2', 'qty_surface_m2')


class ConstructionMaterialNeed(models.Model):
    """Besoin matière d'une phase : ce qu'il faut d'un matériau pour la
    réaliser, d'après le métré de son élément et la nomenclature de la phase.

        besoin = métré x (quantité de la ligne / quantité de référence)
                       x coefficient (pertes, réemploi)

    La nomenclature est une nomenclature native (mrp.bom) : chaque ligne vise
    un article Odoo. Le produit retenu est celui que le projet a choisi pour
    la catégorie de matériau de la ligne, ou à défaut l'article de la ligne.
    Le besoin est suivi jusqu'à l'achat et la consommation réelle."""
    _name = 'construction.material.need'
    _description = "Besoin matériau d'une phase"
    _order = 'project_id, ouvrage_task_id, element_id, task_id, sequence, id'
    _rec_name = 'product_id'

    task_id = fields.Many2one(
        'project.task', string="Phase", required=True, ondelete='cascade', index=True)
    element_id = fields.Many2one(
        related='task_id.construction_element_id', store=True, string="Élément")
    project_id = fields.Many2one(
        related='task_id.project_id', store=True, index=True, string="Projet")
    ouvrage_task_id = fields.Many2one(
        related='task_id.parent_id', store=True, string="Ouvrage")
    level_id = fields.Many2one(
        related='element_id.level_id', store=True, string="Niveau")
    element_type_id = fields.Many2one(
        related='element_id.element_type_id', store=True, string="Type d'élément")
    phase_type = fields.Char(related='task_id.phase_type', store=True, string="Phase (code)")

    bom_id = fields.Many2one('mrp.bom', string="Nomenclature", index=True)
    bom_line_id = fields.Many2one(
        'mrp.bom.line', string="Ligne de nomenclature", ondelete='set null')
    sequence = fields.Integer(related='bom_line_id.sequence', store=True)
    category_id = fields.Many2one(
        'construction.material.category', string="Matériau", index=True)
    product_id = fields.Many2one('product.product', string="Produit", index=True)

    base_qty = fields.Float("Métré de la phase", digits=(16, 3))
    base_uom_id = fields.Many2one('uom.uom', string="Unité du métré")
    quantity = fields.Float("Besoin", digits='Product Unit of Measure',
                            help="Dans l'unité de la ligne de nomenclature.")
    uom_id = fields.Many2one('uom.uom', string="Unité", required=True)
    product_qty = fields.Float(
        "Besoin (unité produit)", compute='_compute_product_qty', store=True,
        digits='Product Unit of Measure')
    product_uom_id = fields.Many2one(related='product_id.uom_id', string="Unité produit")
    unit_cost = fields.Float(related='product_id.standard_price', string="Coût unitaire")
    planned_cost = fields.Float("Coût prévu", compute='_compute_product_qty', store=True)

    # --- Achat -------------------------------------------------------------
    purchase_line_id = fields.Many2one(
        'purchase.order.line', string="Ligne d'achat", ondelete='set null', copy=False)
    purchase_id = fields.Many2one(related='purchase_line_id.order_id', string="Achat")
    qty_ordered = fields.Float("Commandé", compute='_compute_progress', store=True,
                               digits='Product Unit of Measure')
    qty_received = fields.Float("Reçu", compute='_compute_progress', store=True,
                                digits='Product Unit of Measure')

    # --- Consommation ------------------------------------------------------
    move_ids = fields.One2many('stock.move', 'construction_need_id', string="Consommations")
    qty_consumed = fields.Float("Consommé", compute='_compute_progress', store=True,
                                digits='Product Unit of Measure')
    qty_remaining = fields.Float("Reste à consommer", compute='_compute_progress',
                                 store=True, digits='Product Unit of Measure')
    qty_gap = fields.Float(
        "Écart réel / prévu", compute='_compute_progress', store=True,
        digits='Product Unit of Measure',
        help="Consommé - prévu. Positif : surconsommation.")

    state = fields.Selection([
        ('no_product', "Produit à choisir"),
        ('to_order', "À commander"),
        ('ordered', "Commandé"),
        ('received', "Reçu"),
        ('consumed', "Consommé"),
    ], compute='_compute_progress', store=True, string="État", index=True)

    @api.depends('quantity', 'uom_id', 'product_id', 'product_id.uom_id',
                 'product_id.standard_price')
    def _compute_product_qty(self):
        for need in self:
            uom = need.product_id.uom_id
            if uom and need.uom_id.category_id == uom.category_id:
                need.product_qty = need.uom_id._compute_quantity(need.quantity, uom, round=False)
            else:
                need.product_qty = need.quantity
            need.planned_cost = need.product_qty * (need.product_id.standard_price or 0.0)

    @api.depends('product_qty', 'product_id', 'purchase_line_id.product_qty',
                 'purchase_line_id.qty_received', 'purchase_line_id.order_id.state',
                 'move_ids.state', 'move_ids.quantity')
    def _compute_progress(self):
        for need in self:
            line = need.purchase_line_id
            ordered = received = 0.0
            if line and line.order_id.state != 'cancel' and line.product_qty:
                # Une ligne d'achat regroupe les besoins d'un même produit :
                # chacun en reçoit sa part.
                share = min(need.product_qty / line.product_qty, 1.0)
                ordered = need.product_qty if line.order_id.state in ('purchase', 'done') else 0.0
                received = line.qty_received * share
            consumed = sum(m.product_uom._compute_quantity(m.quantity, m.product_id.uom_id, round=False)
                           for m in need.move_ids if m.state == 'done')
            need.qty_ordered = ordered
            need.qty_received = min(received, need.product_qty)
            need.qty_consumed = consumed
            need.qty_remaining = max(need.product_qty - consumed, 0.0)
            need.qty_gap = consumed - need.product_qty if consumed else 0.0
            rounding = need.product_id.uom_id.rounding or 0.001
            if not need.product_id:
                need.state = 'no_product'
            elif consumed and float_compare(consumed, need.product_qty, precision_rounding=rounding) >= 0:
                need.state = 'consumed'
            elif line and float_compare(received, need.product_qty, precision_rounding=rounding) >= 0:
                need.state = 'received'
            elif line and line.order_id.state != 'cancel':
                need.state = 'ordered'
            else:
                need.state = 'to_order'

    def _is_locked(self):
        """Commandé ou déjà consommé : le besoin a servi, on ne le réécrit plus."""
        self.ensure_one()
        return bool((self.purchase_line_id and self.purchase_line_id.order_id.state != 'cancel')
                    or self.move_ids.filtered(lambda m: m.state == 'done'))

    @api.model
    def _consume(self, quantities, location, origin=False):
        """Sort du stock `location` vers « Consommation chantier » les
        quantités réellement mises en œuvre : {besoin: quantité dans l'unité
        du produit}. Le coût du produit au jour de la sortie reste sur le
        mouvement (price_unit) : il fait le coût réel de la phase."""
        destination = self.env.ref('miro_construction_bom.stock_location_site_consumption')
        moves = self.env['stock.move']
        quantities = {need: qty for need, qty in quantities.items() if qty > 0}
        for need, qty in quantities.items():
            moves |= moves.create({
                'name': _("%(task)s — %(mat)s") % {'task': need.task_id.name,
                                                   'mat': need.category_id.name},
                'origin': origin or need.project_id.name,
                'product_id': need.product_id.id,
                'product_uom': need.product_id.uom_id.id,
                'product_uom_qty': qty,
                'price_unit': need.product_id.standard_price,
                'location_id': location.id,
                'location_dest_id': destination.id,
                'construction_need_id': need.id,
            })
        moves._action_confirm()
        moves._action_assign()
        for move, qty in zip(moves, quantities.values()):
            # Le chantier consomme ce qu'il a réellement mis en œuvre, même
            # si le stock informatique ne le couvre pas entièrement.
            move.quantity = qty
            move.picked = True
        moves._action_done()
        return moves


class ProjectTask(models.Model):
    _inherit = 'project.task'

    material_need_ids = fields.One2many(
        'construction.material.need', 'task_id', string="Besoins matériaux")
    material_need_count = fields.Integer(compute='_compute_material_need_count')

    @api.depends('material_need_ids')
    def _compute_material_need_count(self):
        for task in self:
            task.material_need_count = len(task.material_need_ids)

    def _phase_started(self):
        """Même règle que le recalcul des heures (_refresh_phase_hours)."""
        self.ensure_one()
        return bool(self.x_avancement_global) or self.state in ('1_done', '1_canceled')

    def _refresh_material_needs(self, force=False):
        """Recalcule les besoins des phases. Une phase commencée garde les
        siens (ils ont pu servir à commander), sauf `force`. Un besoin déjà
        commandé ou consommé n'est jamais supprimé ni réécrit. Retourne les
        phases recalculées."""
        Need = self.env['construction.material.need']
        Bom = self.env['mrp.bom']
        refreshed = self.browse()
        for task in self.filtered(lambda t: t.construction_element_id and t.phase_template_line_id):
            if not force and task._phase_started():
                continue
            element = task.construction_element_id
            line = task.phase_template_line_id
            bom = element.element_type_id._bom_for(line) if element.element_type_id else line.bom_id
            existing = {n.bom_line_id.id: n for n in task.material_need_ids}
            wanted = {}

            native = Bom._native_uom(line.qty_key)
            if bom and native and bom.product_qty:
                base = getattr(element, 'qty_%s' % line.qty_key, 0.0) or 0.0
                # Métré exprimé dans l'unité de la nomenclature. Sans arrondi :
                # à la précision du m³ (0,01), 0,252 m³ deviendrait 0,26 avant
                # même d'être multiplié par 350 kg.
                base_in_bom = native._compute_quantity(base, bom.product_uom_id, round=False)
                choices = task.project_id._material_choices()
                for bom_line, quantity in bom._construction_explode(base_in_bom):
                    category = bom_line.material_category_id
                    wanted[bom_line.id] = {
                        'task_id': task.id,
                        'bom_id': bom.id,
                        'bom_line_id': bom_line.id,
                        'category_id': category.id,
                        'product_id': (task.project_id._product_for(category, choices)
                                       or bom_line.product_id).id,
                        'base_qty': base,
                        'base_uom_id': native.id,
                        'quantity': quantity,
                        'uom_id': bom_line.product_uom_id.id,
                    }

            to_create = []
            for line_id, vals in wanted.items():
                need = existing.pop(line_id, None)
                if not need:
                    to_create.append(vals)
                elif not need._is_locked():
                    need.write(vals)
            Need.create(to_create)
            # Lignes disparues de la nomenclature (ou plus de nomenclature)
            stale = Need.browse([n.id for n in existing.values() if not n._is_locked()])
            stale.unlink()
            refreshed |= task
        return refreshed

    def _material_progress(self):
        """Part des matériaux de la phase déjà mise en œuvre (%), pondérée par
        le coût prévu ; à coût nul, moyenne des ratios en quantité. Une
        surconsommation ne compte pas au-delà du prévu. None sans besoin."""
        self.ensure_one()
        needs = self.material_need_ids.filtered(lambda n: n.product_id and n.product_qty > 0)
        if not needs:
            return None
        ratios = [(min(n.qty_consumed / n.product_qty, 1.0), n.planned_cost) for n in needs]
        total_cost = sum(cost for _ratio, cost in ratios)
        if total_cost:
            return 100.0 * sum(ratio * cost for ratio, cost in ratios) / total_cost
        return 100.0 * sum(ratio for ratio, _cost in ratios) / len(ratios)

    def action_refresh_material_needs(self):
        self._refresh_material_needs(force=True)
        return True

    def action_declare_consumption(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _("Déclarer la consommation"),
            'res_model': 'construction.need.consume.wizard', 'view_mode': 'form',
            'target': 'new', 'context': {'default_task_id': self.id},
        }


class ConstructionElement(models.Model):
    """Un métré qui change (hauteur reçue du plan de détail, ouverture
    déduite d'un mur...) recalcule les besoins de ses phases non commencées."""
    _inherit = 'construction.element'

    material_need_ids = fields.One2many(
        'construction.material.need', 'element_id', string="Besoins matériaux")

    def write(self, vals):
        res = super().write(vals)
        if set(QTY_FIELDS) & set(vals):
            self.task_ids._refresh_material_needs()
        return res

    def _generate_tasks(self):
        tasks = super()._generate_tasks()
        tasks._refresh_material_needs()
        return tasks


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    construction_need_ids = fields.One2many(
        'construction.material.need', 'purchase_line_id', string="Besoins chantier")


class StockMove(models.Model):
    _inherit = 'stock.move'

    construction_need_id = fields.Many2one(
        'construction.material.need', string="Besoin chantier", index=True,
        ondelete='set null')
