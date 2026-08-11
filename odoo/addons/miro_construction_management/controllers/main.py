import base64
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError
from odoo.tools import config
class ConstructionDwgController(http.Controller):


    @http.route('/dxf/<int:doc_id>', type='http', auth='user', methods=['GET'])
    def get_dxf(self, doc_id, **kwargs):
        try:
            record = request.env['construction.dwg.files'].browse(doc_id)
            if not record.exists():
                return request.not_found()
            if not record.dxf_file:
                return request.not_found()
            file_content = base64.b64decode(record.dxf_file)
        except AccessError:
            return request.make_response('Accès refusé', status=403)

        filename = record.dxf_filename or f"{record.filename}.dxf"
        
        construction_frontend_url = config.get(
            'construction_frontend_url' 
        )

        return request.make_response(
            file_content,
            headers=[
                ('Content-Type', 'application/dxf'),
                ('Content-Disposition', f'inline; filename="{filename}"'),
                ('Access-Control-Allow-Origin', construction_frontend_url),
                ('Access-Control-Allow-Credentials', 'true'),
                ('Cache-Control', 'no-cache'),
            ],
        )