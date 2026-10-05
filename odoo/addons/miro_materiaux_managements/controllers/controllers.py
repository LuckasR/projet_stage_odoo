from odoo import http
from odoo.http import request

class Miro_materiaux_managementsController(http.Controller):

    @http.route('/miro_materiaux_managements/test', type='http', auth='public')
    def test(self, **kwargs):
        return "<h1>Hello Miro_materiaux_managements</h1>"
