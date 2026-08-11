from odoo import models, fields, api

class Miro_custom_moduleModel(models.Model):
    _name = 'miro_custom_module.model'
    _description = 'Miro_custom_module Model'
    
    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')
