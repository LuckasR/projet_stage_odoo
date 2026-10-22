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
    update_progress = fields.Boolean(
        "Mettre à jour l'avancement", default=True,
        help="Porte l'avancement de la phase à la part des matériaux consommée "
             "(pondérée par le coût prévu). Ne le fait jamais baisser.")

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
        self.env['construction.material.need']._consume(
            {line.need_id: line.quantity for line in lines}, self.location_id,
            origin=self.task_id.project_id.name)
        task = self.task_id
        if self.update_progress and not task.child_ids:
            progress = task._material_progress()
            if progress is not None and progress > task.x_avancement_manuel:
                task.x_avancement_manuel = round(progress, 1)
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
