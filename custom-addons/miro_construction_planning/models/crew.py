from odoo import api, fields, models


class MiroCrew(models.Model):
    """Équipe type : sa composition fixe l'effectif mobilisé et le coût
    horaire d'une phase réalisée par elle."""
    _name = 'miro.crew'
    _description = "Équipe type"
    _order = 'sequence, name'

    name = fields.Char("Équipe", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    line_ids = fields.One2many('miro.crew.line', 'crew_id', string="Composition", copy=True)
    headcount = fields.Integer("Effectif", compute='_compute_totals')
    hourly_cost = fields.Monetary(
        "Coût horaire de l'équipe", compute='_compute_totals',
        help="Somme des coûts horaires chargés de ses membres.")
    composition = fields.Char("Composition", compute='_compute_totals')
    note = fields.Text("Note")
    color = fields.Char(
        "Couleur", help="Couleur des barres de cette équipe dans le Gantt (#RRGGBB). "
                        "Vide : couleur automatique.")

    @api.depends('line_ids.quantity', 'line_ids.trade_id', 'line_ids.trade_id.hourly_cost')
    def _compute_totals(self):
        for crew in self:
            crew.headcount = sum(crew.line_ids.mapped('quantity'))
            crew.hourly_cost = sum(l.quantity * l.trade_id.hourly_cost for l in crew.line_ids)
            crew.composition = " + ".join(
                "%d %s" % (l.quantity, l.trade_id.name) for l in crew.line_ids if l.quantity)

    def write(self, vals):
        res = super().write(vals)
        if 'line_ids' in vals:
            self.env['miro.crew.rate'].search([('crew_id', 'in', self.ids)])._refresh_phases()
        return res


class MiroCrewLine(models.Model):
    _name = 'miro.crew.line'
    _description = "Membre d'une équipe type"

    crew_id = fields.Many2one('miro.crew', required=True, ondelete='cascade', index=True)
    trade_id = fields.Many2one('miro.trade', string="Métier", required=True)
    quantity = fields.Integer("Nombre", default=1, required=True)
    currency_id = fields.Many2one(related='crew_id.currency_id')
    hourly_cost = fields.Monetary(related='trade_id.hourly_cost', string="Coût horaire unitaire")
