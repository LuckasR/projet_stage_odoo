from odoo import api, fields, models


class ConstructionPhaseTemplate(models.Model):
    _name = 'construction.phase.template'
    _description = "Gabarit de phases"
    _order = 'name'

    name = fields.Char("Nom", required=True)
    line_ids = fields.One2many(
        'construction.phase.template.line', 'template_id', string="Phases", copy=True)
    active = fields.Boolean(default=True)


class ConstructionPhaseTemplateLine(models.Model):
    _name = 'construction.phase.template.line'
    _description = "Ligne de gabarit de phases"
    _order = 'template_id, sequence, id'

    template_id = fields.Many2one(
        'construction.phase.template', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char("Phase", required=True)
    phase_type = fields.Char(
        "Code de phase", required=True,
        help="Identifiant stable de la phase (ex. : ferraillage). "
             "Sert à ne jamais créer deux fois la même phase sur un élément.")
    depends_on_line_id = fields.Many2one(
        'construction.phase.template.line', string="Dépend de",
        domain="[('template_id', '=', template_id), ('id', '!=', id)]")
    qty_key = fields.Selection(
        [('beton_m3', "Béton (m³)"),
         ('acier_kg', "Acier (kg)"),
         ('coffrage_m2', "Coffrage (m²)")],
        string="Quantité de référence")
    rate_per_hour = fields.Float(
        "Rendement (unité/heure)",
        help="Quantité traitée par heure. Heures prévues = quantité / rendement.")
    fixed_hours = fields.Float(
        "Heures forfaitaires",
        help="Utilisé si aucune quantité de référence ou aucun rendement n'est défini.")

    def _compute_hours(self, element):
        """Heures prévues pour cette phase sur un élément donné."""
        self.ensure_one()
        if self.qty_key and self.rate_per_hour:
            qty = getattr(element, 'qty_%s' % self.qty_key, 0.0) or 0.0
            return qty / self.rate_per_hour
        return self.fixed_hours
