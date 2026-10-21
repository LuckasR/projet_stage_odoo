from odoo import fields, models


class ResCompany(models.Model):
    """Paramètres de paie de la société. Taux et barèmes livrés à titre
    indicatif (Madagascar) : à faire valider par le service comptable."""
    _inherit = 'res.company'

    # --- Temps de travail -------------------------------------------------
    miro_hours_per_day = fields.Float(
        "Heures normales par jour", default=8.0,
        help="Au-delà, les heures d'une journée sont des heures supplémentaires.")
    miro_month_days = fields.Float(
        "Jours de référence par mois", default=26.0,
        help="Sert à ramener un salaire mensuel à la journée (absences, heures "
             "supplémentaires des mensuels). 26 pour une semaine de 6 jours.")
    miro_overtime_rate = fields.Float(
        "Majoration des heures supplémentaires (%)", default=30.0)
    miro_deduct_absences = fields.Boolean(
        "Déduire les absences des mensuels", default=True,
        help="Les jours ouvrés du calendrier sans aucune présence sont retirés "
             "du salaire mensuel, au prorata des jours de référence.")

    # --- Cotisations sociales --------------------------------------------
    miro_cnaps_employee_rate = fields.Float("CNaPS — part salariale (%)", default=1.0)
    miro_cnaps_employer_rate = fields.Float("CNaPS — part patronale (%)", default=13.0)
    miro_cnaps_ceiling = fields.Monetary(
        "Plafond CNaPS", help="Base maximale des cotisations CNaPS (0 = sans plafond).")
    miro_health_label = fields.Char("Organisme de santé", default="OSTIE")
    miro_health_employee_rate = fields.Float("Santé — part salariale (%)", default=1.0)
    miro_health_employer_rate = fields.Float("Santé — part patronale (%)", default=5.0)
    miro_health_ceiling = fields.Monetary(
        "Plafond santé", help="Base maximale des cotisations santé (0 = sans plafond).")

    # --- Impôt sur le revenu (IRSA) --------------------------------------
    miro_irsa_bracket_ids = fields.One2many(
        'miro.irsa.bracket', 'company_id', string="Barème IRSA")
    miro_irsa_minimum = fields.Monetary(
        "IRSA minimum", default=3000.0,
        help="Minimum de perception dès que le revenu imposable dépasse la "
             "tranche exonérée.")
    miro_irsa_dependent_reduction = fields.Monetary(
        "Réduction IRSA par personne à charge", default=2000.0)
