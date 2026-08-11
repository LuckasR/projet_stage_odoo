from odoo import http
from odoo.http import request

class Miro_custom_moduleController(http.Controller):
    
    @http.route('/miro_custom_module/test', type='http', auth='public')
    def test(self, **kwargs):
        return "<h1>Hello Miro_custom_module</h1>"
