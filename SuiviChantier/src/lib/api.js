// Client de l'API Odoo (module miro_mobile_api). Pas de session ni de
// cookie : chaque requête porte le jeton de l'appareil.

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message)
    this.status = status // 0 : serveur injoignable (hors-ligne)
    this.code = code
  }
}

export function normaliserUrl(url) {
  const u = url.trim().replace(/\/+$/, '')
  return /^https?:\/\//.test(u) ? u : `http://${u}`
}

function nomAppareil() {
  const modele = navigator.userAgent.match(/Android [\d.]+; ([^;)]+)/)?.[1]
  return modele ? `Android — ${modele.replace(/ Build.*/, '')}` : 'Téléphone'
}

async function request(session, path, { method = 'GET', json, form } = {}) {
  const headers = {}
  if (session.token) headers.Authorization = `Bearer ${session.token}`
  if (json) headers['Content-Type'] = 'application/json'
  let res
  try {
    res = await fetch(`${session.url}/api/mobile/v1${path}`, {
      method,
      headers,
      body: json ? JSON.stringify(json) : form,
    })
  } catch {
    throw new ApiError(0, 'offline', 'Serveur injoignable.')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.error?.code ?? 'http', body.error?.message ?? `Erreur ${res.status}`)
  }
  return res
}

export const api = {
  login: (url, login, password) =>
    request({ url }, '/login', {
      method: 'POST',
      json: { login, password, device_name: nomAppareil() },
    }).then((r) => r.json()),

  logout: (session) => request(session, '/logout', { method: 'POST' }),

  pull: (session) => request(session, '/sync/pull').then((r) => r.json()),

  push: (session, ops) =>
    request(session, '/sync/push', { method: 'POST', json: { ops } }).then((r) => r.json()),

  uploadPhoto: (session, { uuid, model, resId, blob }) => {
    const form = new FormData()
    form.append('uuid', uuid)
    form.append('model', model)
    form.append('res_id', String(resId))
    form.append('file', blob, `${uuid}.jpg`)
    return request(session, '/photos', { method: 'POST', form }).then((r) => r.json())
  },

  photo: (session, id) => request(session, `/photos/${id}`).then((r) => r.blob()),
}
