from odoo import fields, models


class MiroPlanningLoad(models.Model):
    """Charge d'un métier, jour par jour, d'après le dernier planning du
    chantier : sert aux vues graphique et tableau croisé (« quand manque-t-on
    de maçons ? »)."""
    _name = 'miro.planning.load'
    _description = "Charge par métier et par jour"
    _order = 'date, trade_id'

    project_id = fields.Many2one('project.project', required=True, ondelete='cascade', index=True)
    date = fields.Date("Jour", required=True, index=True)
    trade_id = fields.Many2one('miro.trade', string="Métier", required=True, ondelete='cascade')
    needed = fields.Integer("Personnes mobilisées", group_operator='max',
                            help="Pointe de la journée : nombre de personnes du métier "
                                 "travaillant en même temps.")
    available = fields.Integer(
        "Effectif proposé", group_operator='max',
        help="Pointe du métier sur tout le planning : l'effectif à prévoir.")
    person_hours = fields.Float("Heures-personnes", digits=(16, 2))
    usage_pct = fields.Float("Occupation (%)", group_operator='max', digits=(16, 0))
    saturated = fields.Boolean("Jour de pointe", help="Tout l'effectif proposé du métier est mobilisé.")
