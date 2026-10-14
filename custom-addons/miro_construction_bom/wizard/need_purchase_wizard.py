from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class NeedPurchaseWizard(models.TransientModel):
    """Demandes de prix à partir des besoins « à commander » d'un projet :
    regroupés par produit, diminués du stock disponible si demandé, puis
    répartis en une demande par fournisseur."""
    _name = 'construction.need.purchase.wizard'
    _description = "Demandes de prix depuis les besoins matériaux"

    project_id = fields.Many2one('project.project', required=True)
    deduct_stock = fields.Boolean(
        "Déduire le stock disponible", default=True,
        help="Ne commande que ce qui manque en stock. Le stock n'est pas "
             "réservé au projet : il peut servir à d'autres chantiers.")
    line_ids = fields.One2many('construction.need.purchase.wizard.line', 'wizard_id')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        project = self.env['project.project'].browse(res.get('project_id'))
        if project and 'line_ids' in fields_list:
            res['line_ids'] = self._lines_for(project, res.get('deduct_stock', True))
        return res

    @api.onchange('deduct_stock')
    def _onchange_deduct_stock(self):
        for line in self.line_ids:
            line.to_order_qty = line._suggested_qty(self.deduct_stock)

    @api.model
    def _lines_for(self, project, deduct):
        needs = self.env['construction.material.need'].search([
            ('project_id', '=', project.id), ('state', '=', 'to_order')])
        by_product = defaultdict(lambda: self.env['construction.material.need'])
        for need in needs:
            by_product[need.product_id] |= need
        commands = []
        for product, group in by_product.items():
            needed = sum(group.mapped('product_qty'))
            available = max(product.qty_available, 0.0)
            seller = product._select_seller(quantity=needed)
            commands.append(Command.create({
                'product_id': product.id,
                'need_ids': [Command.set(group.ids)],
                'needed_qty': needed,
                'available_qty': available,
                'to_order_qty': max(needed - available, 0.0) if deduct else needed,
                'partner_id': seller.partner_id.id,
                'price_unit': seller.price if seller else product.standard_price,
            }))
        return commands

    def action_create(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.to_order_qty > 0)
        if not lines:
            raise UserError(_("Rien à commander : le stock couvre les besoins, ou "
                              "aucun besoin n'est à commander."))
        missing = lines.filtered(lambda l: not l.partner_id)
        if missing:
            raise UserError(_("Choisissez un fournisseur pour : %s")
                            % ", ".join(missing.product_id.mapped('display_name')))

        orders = self.env['purchase.order']
        for partner in lines.partner_id:
            order = orders.create({
                'partner_id': partner.id,
                'origin': self.project_id.name,
                'order_line': [Command.create({
                    'product_id': l.product_id.id,
                    'product_qty': l.to_order_qty,
                    'product_uom': l.product_id.uom_po_id.id or l.product_id.uom_id.id,
                    'price_unit': l.price_unit,
                    'date_planned': fields.Datetime.now(),
                }) for l in lines.filtered(lambda l, p=partner: l.partner_id == p)],
            })
            for po_line in order.order_line:
                wizard_line = lines.filtered(
                    lambda l, p=po_line: l.partner_id == partner and l.product_id == p.product_id)
                wizard_line.need_ids.write({'purchase_line_id': po_line.id})
            orders |= order
        return {
            'type': 'ir.actions.act_window', 'name': _("Demandes de prix"),
            'res_model': 'purchase.order',
            'view_mode': 'form' if len(orders) == 1 else 'tree,form',
            'res_id': orders.id if len(orders) == 1 else False,
            'domain': [('id', 'in', orders.ids)],
        }


class NeedPurchaseWizardLine(models.TransientModel):
    _name = 'construction.need.purchase.wizard.line'
    _description = "Ligne de demande de prix matériaux"

    wizard_id = fields.Many2one('construction.need.purchase.wizard', required=True,
                                ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Produit", required=True)
    uom_id = fields.Many2one(related='product_id.uom_id', string="Unité")
    need_ids = fields.Many2many('construction.material.need', 'construction_need_po_wizard_rel',
                                'line_id', 'need_id', string="Besoins")
    needed_qty = fields.Float("Besoin", digits='Product Unit of Measure', readonly=True)
    available_qty = fields.Float("En stock", digits='Product Unit of Measure', readonly=True)
    to_order_qty = fields.Float("À commander", digits='Product Unit of Measure')
    partner_id = fields.Many2one('res.partner', string="Fournisseur")
    price_unit = fields.Float("Prix unitaire", digits='Product Price')

    def _suggested_qty(self, deduct):
        self.ensure_one()
        return max(self.needed_qty - self.available_qty, 0.0) if deduct else self.needed_qty
