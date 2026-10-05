from odoo import models, fields

class ProductTemplateInherit(models.Model): 
    _inherit = 'product.template'

    x_reference_miro = fields.Char(string='Référence Miro')
    x_notes_materiaux = fields.Text(string='Notes matériaux')