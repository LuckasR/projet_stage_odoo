from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class NeedConsumeWizard(models.TransientModel):
    """Consommation réelle d'une phase : chaque matériau mis en œuvre sort du
    stock vers l'emplacement « Consommation chantier ». C'est elle qui
    alimente l'écart réel / prévu des besoins."""
    _name = 'construction.need.consume.wizard'
    _description = "Déclaration de consommation de matériaux"

    task_id = fields.Many2one('project.task', string="Phase", required=True)
    location_id = fields.Many2one(
        'stock.location', string="Depuis", required=True,
        domain=[('usage', '=', 'internal')],
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1).lot_stock_id)
    line_ids = fields.One2many('construction.need.consume.wizard.line', 'wizard_id')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        task = self.env['project.task'].browse(res.get('task_id'))
        if task and 'line_ids' in fields_list:
            res['line_ids'] = [Command.create({
                'need_id': need.id, 'quantity': need.qty_remaining})
                for need in task.material_need_ids.filtered('product_id')]
        return res

    def action_confirm(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.quantity > 0)
        if not lines:
            raise UserError(_("Aucune quantité consommée saisie."))
        destination = self.env.ref('miro_construction_bom.stock_location_site_consumption')
        moves = self.env['stock.move']
        for line in lines:
            need = line.need_id
            moves |= moves.create({
                'name': _("%(task)s — %(mat)s") % {'task': self.task_id.name,
                                                   'mat': need.category_id.name},
                'origin': self.task_id.project_id.name,
                'product_id': need.product_id.id,
                'product_uom': need.product_id.uom_id.id,
                'product_uom_qty': line.quantity,
                'location_id': self.location_id.id,
                'location_dest_id': destination.id,
                'construction_need_id': need.id,
            })
        moves._action_confirm()
        moves._action_assign()
        for move, line in zip(moves, lines):
            # Le chantier consomme ce qu'il a réellement mis en œuvre, même
            # si le stock informatique ne le couvre pas entièrement.
            move.quantity = line.quantity
            move.picked = True
        moves._action_done()
        return {'type': 'ir.actions.act_window_close'}


class NeedConsumeWizardLine(models.TransientModel):
    _name = 'construction.need.consume.wizard.line'
    _description = "Ligne de consommation de matériaux"

    wizard_id = fields.Many2one('construction.need.consume.wizard', required=True,
                                ondelete='cascade')
    need_id = fields.Many2one('construction.material.need', required=True, string="Besoin")
    category_id = fields.Many2one(related='need_id.category_id')
    product_id = fields.Many2one(related='need_id.product_id')
    planned_qty = fields.Float(related='need_id.product_qty', string="Prévu")
    consumed_qty = fields.Float(related='need_id.qty_consumed', string="Déjà consommé")
    uom_id = fields.Many2one(related='need_id.product_uom_id', string="Unité")
    quantity = fields.Float("Consommé maintenant", digits='Product Unit of Measure')
