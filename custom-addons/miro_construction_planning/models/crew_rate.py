from collections import Counter

from odoo import _, api, fields, models

QTY_KEYS = [
    ('beton_m3', "m³ de béton"),
    ('acier_kg', "kg d'acier"),
    ('coffrage_m2', "m² de coffrage"),
    ('surface_m2', "m² de surface"),
]


class MiroCrewRate(models.Model):
    """Cadence : ce qu'une équipe produit en une heure sur un type de phase.

        durée (h) = quantité de la phase ÷ cadence
        heures-personnes = durée × effectif de l'équipe
        coût = durée × coût horaire de l'équipe

    Une cadence propre à un type d'élément (coffrage d'un poteau) passe avant
    la cadence générale du type de phase (coffrage)."""
    _name = 'miro.crew.rate'
    _description = "Cadence d'une équipe"
    _order = 'phase_type, element_type_id, sequence, id'
    _rec_name = 'crew_id'

    sequence = fields.Integer(default=10)
    phase_type = fields.Selection(
        selection='_selection_phase_type', string="Type de phase", required=True,
        help="Code de phase des gabarits (coffrage, ferraillage, coulage...).")
    element_type_id = fields.Many2one(
        'construction.element.type', string="Type d'élément",
        help="Vide : cadence valable pour tous les types d'éléments.")
    crew_id = fields.Many2one('miro.crew', string="Équipe", required=True, ondelete='cascade')
    rate = fields.Float("Cadence (par heure)", required=True, digits=(16, 3), group_operator=False,
                        help="Quantité produite par l'équipe en une heure.")
    qty_key = fields.Selection(QTY_KEYS, string="Unité",
                               help="Rappel : l'unité est celle de la quantité de référence de la phase.")
    is_default = fields.Boolean(
        "Équipe par défaut",
        help="Équipe retenue pour chiffrer la phase tant que le planning n'en a "
             "pas choisi une autre.")
    headcount = fields.Integer(related='crew_id.headcount', group_operator=False)
    currency_id = fields.Many2one(related='crew_id.currency_id')
    crew_hourly_cost = fields.Monetary(related='crew_id.hourly_cost', string="Coût horaire équipe")
    unit_cost = fields.Monetary(
        "Coût unitaire", compute='_compute_unit_cost',
        help="Coût de main-d'œuvre d'une unité produite (coût horaire ÷ cadence).")
    note = fields.Char("Note")

    @api.model
    def _selection_phase_type(self):
        # Libellé le plus courant d'un code de phase (« Coffrage » plutôt que
        # « Étaiement et coffrage », propre au gabarit des dalles)
        names = {}
        for line in self.env['construction.phase.template.line'].sudo().search([]):
            names.setdefault(line.phase_type, Counter())[line.name] += 1
        return sorted(((code, counter.most_common(1)[0][0]) for code, counter in names.items()),
                      key=lambda kv: kv[1])

    @api.depends('rate', 'crew_id.hourly_cost')
    def _compute_unit_cost(self):
        for rec in self:
            rec.unit_cost = rec.crew_hourly_cost / rec.rate if rec.rate else 0.0

    @api.model
    def _rate_for(self, phase_type, element_type):
        """Cadence retenue pour une phase : celle du type d'élément avant la
        générale, l'équipe par défaut avant les autres."""
        rates = self.search([('phase_type', '=', phase_type),
                             ('element_type_id', 'in', [element_type.id, False]),
                             ('rate', '>', 0)])
        if not rates:
            return rates
        return rates.sorted(lambda r: (not r.element_type_id, not r.is_default, r.sequence, r.id))[:1]

    # --- Recalcul des phases concernées --------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        rates = super().create(vals_list)
        rates._refresh_phases()
        return rates

    def write(self, vals):
        res = super().write(vals)
        self._refresh_phases()
        return res

    def unlink(self):
        phase_types = set(self.mapped('phase_type'))
        res = super().unlink()
        self.env['project.task'].search([
            ('phase_type', 'in', list(phase_types)), ('construction_element_id', '!=', False),
        ])._miro_refresh_labor()
        return res

    def _refresh_phases(self):
        if not self or self.env.context.get('miro_no_refresh'):
            return
        self.env['project.task'].search([
            ('phase_type', 'in', list(set(self.mapped('phase_type')))),
            ('construction_element_id', '!=', False),
        ])._miro_refresh_labor()
