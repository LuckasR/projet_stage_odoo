from odoo import fields, models


class ConstructionElementType(models.Model):
    _name = 'construction.element.type'
    _description = "Type d'élément de construction"
    _order = 'name'

    name = fields.Char("Nom", required=True, translate=True)
    code = fields.Char(
        "Code d'analyse", required=True,
        help="Valeur du champ « type » renvoyée par l'analyse (ex. : semelle, poteau).")
    work_name = fields.Char(
        "Ouvrage de rattachement", required=True,
        help="Nom de l'ouvrage auquel ce type d'élément est rattaché (ex. : Fondation). "
             "L'ouvrage est créé automatiquement dans le projet s'il n'existe pas.")
    phase_template_id = fields.Many2one(
        'construction.phase.template', string="Gabarit de phases")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', "Ce code de type existe déjà."),
    ]
