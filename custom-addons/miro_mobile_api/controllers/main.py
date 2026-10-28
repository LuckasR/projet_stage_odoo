import functools
import json
import logging

from odoo import _, fields, http
from odoo.exceptions import AccessDenied, AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

PREFIX = '/api/mobile/v1'


def _error(status, code, message):
    return request.make_json_response({'error': {'code': code, 'message': message}}, status=status)


def _body():
    try:
        return json.loads(request.httprequest.get_data() or b'{}')
    except ValueError:
        raise UserError(_("Corps de requête JSON invalide."))


def _guarded(func, *args, **kwargs):
    """Erreurs Odoo -> réponses JSON ; rien de ce qui précède l'erreur
    n'est enregistré."""
    try:
        return func(*args, **kwargs)
    except AccessDenied:
        request.env.cr.rollback()
        return _error(401, 'unauthorized', _("Identifiant ou mot de passe incorrect."))
    except AccessError as e:
        request.env.cr.rollback()
        return _error(403, 'forbidden', str(e.args[0] if e.args else e))
    except UserError as e:
        request.env.cr.rollback()
        return _error(422, 'invalid', str(e.args[0] if e.args else e))


def mobile_auth(func):
    """Authentifie le téléphone par son jeton (en-tête « Authorization:
    Bearer ») et exécute la route sous son utilisateur, qui reçoit
    l'appareil en premier argument."""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        header = request.httprequest.headers.get('Authorization', '')
        token = header[7:].strip() if header.startswith('Bearer ') else ''
        device = request.env['miro.mobile.device']._from_token(token)
        if not device or not device.user_id.active:
            return _error(401, 'unauthorized', _("Session expirée : reconnectez-vous."))
        request.update_env(user=device.user_id.id)
        device = device.with_env(request.env).sudo()
        device.last_seen = fields.Datetime.now()
        return _guarded(func, self, device, *args, **kwargs)
    return wrapper


class MobileApiController(http.Controller):
    """API de l'application SuiviChantier. Sans session ni cookie : chaque
    requête porte le jeton de l'appareil, d'où auth='none' et le CORS
    ouvert (le jeton, lui, ne l'est pas)."""

    @http.route(f'{PREFIX}/login', type='http', auth='none', methods=['POST'],
                csrf=False, cors='*')
    def login(self):
        def do():
            data = _body()
            if not request.db:
                return _error(400, 'no_database', _("Aucune base de données sélectionnée."))
            uid = request.env['res.users'].authenticate(
                request.db, data.get('login'), data.get('password'), {'interactive': False})
            user = request.env['res.users'].sudo().browse(uid)
            if not user._is_internal():
                return _error(403, 'forbidden', _("Compte non autorisé sur l'application."))
            token = request.env['miro.mobile.device']._issue(
                user, data.get('device_name') or _("Téléphone"))
            return request.make_json_response(
                {'token': token, 'user': {'id': user.id, 'name': user.name}})
        return _guarded(do)

    @http.route(f'{PREFIX}/logout', type='http', auth='none', methods=['POST'],
                csrf=False, cors='*')
    @mobile_auth
    def logout(self, device):
        device.action_revoke()
        return request.make_json_response({'status': 'ok'})

    @http.route(f'{PREFIX}/sync/pull', type='http', auth='none', methods=['GET'],
                csrf=False, cors='*')
    @mobile_auth
    def pull(self, device):
        return request.make_json_response(request.env['miro.mobile.api']._snapshot())

    @http.route(f'{PREFIX}/sync/push', type='http', auth='none', methods=['POST'],
                csrf=False, cors='*')
    @mobile_auth
    def push(self, device):
        ops = _body().get('ops') or []
        results = request.env['miro.mobile.api']._push(ops, device)
        return request.make_json_response({'results': results})

    @http.route(f'{PREFIX}/photos', type='http', auth='none', methods=['POST'],
                csrf=False, cors='*')
    @mobile_auth
    def upload_photo(self, device, uuid=None, model=None, res_id=None, file=None, **kw):
        result = request.env['miro.mobile.api']._upload_photo(device, uuid, model, res_id, file)
        return request.make_json_response(result)

    @http.route(f'{PREFIX}/photos/<int:attachment_id>', type='http', auth='none',
                methods=['GET'], csrf=False, cors='*')
    @mobile_auth
    def photo(self, device, attachment_id):
        attachment = request.env['miro.mobile.api']._photo(attachment_id)
        return request.make_response(attachment.raw, headers=[
            ('Content-Type', attachment.mimetype or 'image/jpeg'),
            ('Cache-Control', 'private, max-age=604800'),
        ])
