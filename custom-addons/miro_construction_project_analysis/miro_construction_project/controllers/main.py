import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        headers=[('Content-Type', 'application/json')],
        status=status)


class ConstructionAnalysisController(http.Controller):

    @http.route('/construction/analysis/result', type='http', auth='public',
                methods=['POST'], csrf=False)
    def analysis_result(self, **kwargs):
        """Callback du service d'analyse.

        Header requis : X-Miro-Token (= paramètre système miro_construction.api_token).
        Corps : JSON brut, voir le contrat dans construction.analysis._process_result.
        Avec plusieurs bases : ajouter ?db=nom_base à l'URL.
        """
        env = request.env(su=True)
        expected = env['ir.config_parameter'].get_param('miro_construction.api_token') or ''
        received = request.httprequest.headers.get('X-Miro-Token', '')
        if not expected or not hmac.compare_digest(expected, received):
            return _json_response({'error': 'unauthorized'}, 401)

        try:
            data = json.loads(request.httprequest.get_data(as_text=True))
        except ValueError:
            return _json_response({'error': 'invalid json'}, 400)

        analysis = env['construction.analysis'].browse(
            int(data.get('analysis_id') or 0)).exists()
        if not analysis:
            return _json_response({'error': 'analysis not found'}, 404)
        if analysis.state != 'running':
            return _json_response({'error': 'analysis not running'}, 409)

        try:
            with env.cr.savepoint():
                analysis.write({'payload_json': json.dumps(data, ensure_ascii=False)})
                analysis._process_result(data)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Résultat d'analyse %s invalide", analysis.id)
            analysis.write({'state': 'failed', 'error_log': str(exc)})
            return _json_response({'error': str(exc)}, 422)

        return _json_response({'status': 'ok', 'drafts': analysis.draft_count})
