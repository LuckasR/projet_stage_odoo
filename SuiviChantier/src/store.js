import { useSyncExternalStore } from 'react'
import { ApiError, api } from './lib/api.js'
import { kv, photoStore } from './lib/db.js'

/* ---------- Utilitaires ---------- */

export const newId = () =>
  crypto.randomUUID?.() ?? Math.random().toString(36).slice(2) + Date.now().toString(36)

export function today() {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 10)
}

export function addDays(iso, days) {
  const d = new Date(iso + 'T12:00:00')
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

export function formatDate(iso, opts = { day: 'numeric', month: 'short', year: 'numeric' }) {
  if (!iso) return '—'
  return new Date(iso.slice(0, 10) + 'T12:00:00').toLocaleDateString('fr-FR', opts)
}

/** 28.10.2025, comme sur les maquettes */
export const dateCourte = (iso) => (iso ? iso.slice(0, 10).split('-').reverse().join('.') : '—')

export function jourRelatif(iso) {
  if (iso === today()) return "Aujourd'hui"
  if (iso === addDays(today(), -1)) return 'Hier'
  return formatDate(iso, { weekday: 'long', day: 'numeric', month: 'long' })
}

export const nombre = (n, max = 2) =>
  new Intl.NumberFormat('fr-FR', { maximumFractionDigits: max }).format(Number(n) || 0)

export function argent(n, devise = 'EUR') {
  try {
    return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: devise, maximumFractionDigits: 0 }).format(Number(n) || 0)
  } catch {
    return `${nombre(n, 0)} ${devise}`
  }
}

export const METEO_ICONES = { sunny: '☀️', cloudy: '⛅', rain: '🌧️', storm: '⛈️' }

export const label = (selection, key) => selection?.find(([k]) => k === key)?.[1] ?? key

// Réduit une photo avant stockage : ~150 Ko au lieu de plusieurs Mo.
export function compresserImage(file, max = 1600, quality = 0.7) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, max / Math.max(img.width, img.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.round(img.width * scale)
      canvas.height = Math.round(img.height * scale)
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('Photo illisible'))), 'image/jpeg', quality)
    }
    img.onerror = (e) => {
      URL.revokeObjectURL(url)
      reject(e)
    }
    img.src = url
  })
}

/* ---------- État ----------
 * snapshot : dernière copie des données d'Odoo (lecture seule).
 * journals : en-têtes de journal modifiés sur le téléphone (météo, heures
 *   d'arrêt, observations, frais du chantier, soumission).
 * works : travaux modifiés sur le téléphone, un par uid. Un travail porte
 *   sa propre version : deux personnes peuvent saisir des travaux
 *   différents du même journal sans conflit.
 * incidents : incidents créés ou modifiés sur le téléphone.
 * Chaque saisie a un uuid d'envoi (renouvelé à chaque modification) et la
 * version d'Odoo sur laquelle elle a été faite : c'est ce qui permet à
 * Odoo de détecter un conflit.
 * photos : photos pas encore envoyées (le fichier est dans IndexedDB). */

const PERSISTED = ['session', 'snapshot', 'pulledAt', 'journals', 'works', 'incidents', 'photos']

let state = {
  session: null, // { url, login, token, user }
  snapshot: null,
  pulledAt: null,
  journals: {},
  works: {},
  incidents: {},
  photos: [],
  loaded: false,
  syncing: false,
  online: navigator.onLine,
  syncError: null,
  storageError: false,
}

const listeners = new Set()
let persistTimer

function persist() {
  clearTimeout(persistTimer)
  const data = Object.fromEntries(PERSISTED.map((k) => [k, state[k]]))
  kv.put('state', data).then(
    () => state.storageError && setState(() => ({ storageError: false })),
    () => setState(() => ({ storageError: true })),
  )
}

function setState(fn) {
  const patch = fn(state)
  if (!patch) return
  state = { ...state, ...patch }
  listeners.forEach((l) => l())
  if (PERSISTED.some((k) => k in patch)) {
    clearTimeout(persistTimer)
    persistTimer = setTimeout(persist, 300)
  }
}

export function useApp() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => state,
  )
}

export async function demarrer() {
  let saved = null
  try {
    saved = await kv.get('state')
  } catch {
    /* IndexedDB indisponible : on repart de zéro */
  }
  // Saisies faites avec l'ancienne version (journal envoyé en bloc) : elles
  // ne correspondent plus à l'API ; le journal se rechargera depuis Odoo.
  const ancien = saved && !saved.works
  setState(() => ({ ...saved, ...(ancien && { journals: {}, works: {} }), loaded: true }))

  window.addEventListener('online', () => {
    setState(() => ({ online: true }))
    requestSync(0)
  })
  window.addEventListener('offline', () => setState(() => ({ online: false })))
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') persist()
    else requestSync(0)
  })
  setInterval(() => document.visibilityState === 'visible' && requestSync(0), 120_000)

  if (state.session?.token) requestSync(0)
}

/* ---------- Session ---------- */

export async function connecter(url, login, password) {
  const res = await api.login(url, login, password)
  const autre = state.session?.user && state.session.user.id !== res.user.id
  // Les saisies d'un autre utilisateur ne doivent pas partir sous ce compte
  if (autre) await effacerDonnees()
  setState(() => ({ session: { url, login, token: res.token, user: res.user }, syncError: null }))
  await sync()
}

async function effacerDonnees() {
  await photoStore.clear().catch(() => {})
  setState(() => ({ snapshot: null, pulledAt: null, journals: {}, works: {}, incidents: {}, photos: [] }))
}

export async function deconnecter() {
  const { session } = state
  api.logout(session).catch(() => {})
  await effacerDonnees()
  setState(() => ({ session: { url: session.url, login: session.login, token: null, user: null } }))
}

export const enAttente = (s) =>
  Object.keys(s.journals).length + Object.keys(s.works).length
  + Object.keys(s.incidents).length + s.photos.length

/* ---------- Journaux ---------- */

export const journalKey = (projectId, date) => `${projectId}|${date}`

export const emptyHeader = () => ({
  weather: null, hours_lost: 0, notes: '', site_equipment: [], site_expenses: [],
})

function headerData(j) {
  const { weather, hours_lost, notes, site_equipment, site_expenses } = j
  return structuredClone({ weather, hours_lost, notes: notes ?? '', site_equipment, site_expenses })
}

export function workData(w) {
  const { task_id, qty_done, correction_reason, status, note, labor, materials, equipment, expenses } = w
  return structuredClone({ task_id, qty_done, correction_reason, status, note, labor, materials, equipment, expenses })
}

export const nouveauTravail = (taskId) => ({
  task_id: taskId, qty_done: 0, correction_reason: null, status: 'doing', note: null,
  labor: [], materials: [], equipment: [], expenses: [],
})

const serverJournal = (s, projectId, date) =>
  s.snapshot?.journals.find((j) => j.project_id === projectId && j.date === date)

const serverJournalByKey = (s, key) => {
  const [projectId, date] = key.split('|')
  return serverJournal(s, Number(projectId), date)
}

/** Le journal tel qu'il s'affiche : la version d'Odoo, recouverte par les
 *  saisies du téléphone (en-tête et travaux) pas encore acceptées. */
export function journalView(s, projectId, date) {
  const key = journalKey(projectId, date)
  const server = serverJournal(s, projectId, date)
  const local = s.journals[key]
  const works = []
  for (const w of server?.works ?? []) {
    const lw = s.works[w.uid]
    if (lw?.deleted) continue
    works.push({ uid: w.uid, server: w, local: lw, data: lw?.data ?? workData(w) })
  }
  const locaux = Object.values(s.works)
    .filter((lw) => lw.key === key && !lw.deleted && !server?.works.some((w) => w.uid === lw.uid))
    .sort((a, b) => a.created - b.created)
  for (const lw of locaux) works.push({ uid: lw.uid, server: null, local: lw, data: lw.data })

  const saisies = [local, ...Object.values(s.works).filter((lw) => lw.key === key)].filter(Boolean)
  return {
    key, date, projectId, server, local, works, saisies,
    header: local?.data ?? (server ? headerData(server) : emptyHeader()),
    state: server?.state ?? null,
  }
}

export function projectJournals(s, projectId) {
  const dates = new Set((s.snapshot?.journals ?? []).filter((j) => j.project_id === projectId).map((j) => j.date))
  for (const l of [...Object.values(s.journals), ...Object.values(s.works)]) {
    if (l.project_id === projectId) dates.add(l.date)
  }
  return [...dates].sort((a, b) => b.localeCompare(a)).map((d) => journalView(s, projectId, d))
}

/** Libellé et couleur de l'état d'un journal, saisies locales comprises. */
export function journalStatut(s, vue) {
  if (vue.saisies.some((l) => l.status === 'conflict')) return { label: 'Conflit', tone: 'danger' }
  if (vue.saisies.some((l) => l.status === 'error')) return { label: 'Refusé', tone: 'danger' }
  if (vue.local?.submit) return { label: 'Soumission en attente', tone: 'warn' }
  if (vue.saisies.length) return { label: 'Non envoyé', tone: 'warn' }
  if (!vue.server) return null
  const tones = { draft: 'info', submitted: 'accent', validated: 'success' }
  return { label: label(s.snapshot?.selections.journal_state, vue.server.state), tone: tones[vue.server.state] }
}

/** État d'un travail ou d'une ligne : validé dans Odoo, validation demandée
 *  (en attente d'envoi), ou brouillon modifiable. */
export function etatLigne(serverState, demande) {
  if (serverState === 'validated') return 'validated'
  return demande ? 'pending' : 'draft'
}

function nouvelleSaisie(prev, fields) {
  return {
    ...prev,
    ...fields,
    uuid: newId(),
    status: prev?.status === 'conflict' ? 'conflict' : 'pending',
    conflict: prev?.conflict ?? null,
    error: null,
  }
}

export function saveHeader(projectId, date, data, { submit } = {}) {
  setState((s) => {
    const key = journalKey(projectId, date)
    const prev = s.journals[key]
    return {
      journals: {
        ...s.journals,
        [key]: nouvelleSaisie(prev, {
          key, project_id: projectId, date, data,
          submit: submit ?? prev?.submit ?? false,
          base_version: prev ? prev.base_version : serverJournal(s, projectId, date)?.version ?? null,
        }),
      },
    }
  })
  requestSync()
}

export function saveWork(projectId, date, uid, data, { validate } = {}) {
  setState((s) => {
    const key = journalKey(projectId, date)
    const prev = s.works[uid]
    const server = serverJournal(s, projectId, date)?.works.find((w) => w.uid === uid)
    return {
      works: {
        ...s.works,
        [uid]: nouvelleSaisie(prev, {
          uid, key, project_id: projectId, date, data,
          validate: validate ?? prev?.validate ?? false,
          deleted: false,
          created: prev?.created ?? Date.now(),
          base_version: prev ? prev.base_version : server?.version ?? null,
        }),
      },
    }
  })
  requestSync()
}

export function supprimerWork(projectId, date, uid) {
  setState((s) => {
    const server = serverJournal(s, projectId, date)?.works.find((w) => w.uid === uid)
    const prev = s.works[uid]
    if (!server) {
      const { [uid]: _, ...works } = s.works
      return { works }
    }
    return {
      works: {
        ...s.works,
        [uid]: nouvelleSaisie(prev, {
          uid, key: journalKey(projectId, date), project_id: projectId, date,
          data: prev?.data ?? workData(server), deleted: true, validate: false,
          created: prev?.created ?? Date.now(),
          base_version: prev ? prev.base_version : server.version,
        }),
      },
    }
  })
  requestSync()
}

/** Résout un conflit : garder la version d'Odoo, ou renvoyer la sienne
 *  par-dessus en prenant la version d'Odoo pour base. */
export function resoudre(table, key, choix) {
  setState((s) => {
    const local = s[table][key]
    const record = local.conflict?.record
    if (choix === 'serveur') {
      const { [key]: _, ...rest } = s[table]
      return { [table]: rest, snapshot: record ? withRecord(s.snapshot, recordTable(table), record) : s.snapshot }
    }
    return {
      [table]: {
        ...s[table],
        [key]: { ...local, base_version: versionDe(table, local, record), uuid: newId(), status: 'pending', conflict: null },
      },
    }
  })
  requestSync(0)
}

export function abandonner(table, key) {
  setState((s) => {
    const { [key]: _, ...rest } = s[table]
    return { [table]: rest }
  })
}

const recordTable = (table) => (table === 'incidents' ? 'incidents' : 'journals')

/** Version d'Odoo de la saisie dans un enregistrement renvoyé par Odoo. */
function versionDe(table, local, record) {
  if (!record) return null
  if (table === 'works') return record.works.find((w) => w.uid === local.uid)?.version ?? null
  return record.version
}

/* ---------- Incidents ---------- */

export function incidentsView(s, projectId = null) {
  const list = []
  for (const i of s.snapshot?.incidents ?? []) {
    if (projectId != null && i.project_id !== projectId) continue
    const local = s.incidents[`s-${i.id}`]
    list.push({ ...i, ...local?.data, key: `s-${i.id}`, local })
  }
  for (const l of Object.values(s.incidents)) {
    if (l.id || (projectId != null && l.project_id !== projectId)) continue
    list.push({ id: null, key: l.key, project_id: l.project_id, task_id: l.task_id, photos: [], ...l.data, local: l })
  }
  return list.sort((a, b) => (b.date ?? '').localeCompare(a.date ?? ''))
}

export const nouvelleCleIncident = () => `l-${newId()}`

export function creerIncident(projectId, taskId, data, key = nouvelleCleIncident()) {
  setState((s) => ({
    incidents: {
      ...s.incidents,
      [key]: {
        key, id: null, project_id: projectId, task_id: taskId,
        data: { date: today(), etat: 'ouvert', ...data },
        base_version: null, uuid: newId(), status: 'pending', conflict: null, error: null,
      },
    },
  }))
  requestSync()
  return key
}

export function modifierIncident(incident, changes) {
  setState((s) => {
    const prev = s.incidents[incident.key]
    const next = prev
      ? nouvelleSaisie(prev, { data: { ...prev.data, ...changes } })
      : nouvelleSaisie(null, {
          key: incident.key, id: incident.id, project_id: incident.project_id, task_id: incident.task_id,
          data: changes, base_version: incident.version,
        })
    return { incidents: { ...s.incidents, [incident.key]: next } }
  })
  requestSync()
}

/* ---------- Photos ---------- */

export async function ajouterPhoto(target, ref, file) {
  const blob = await compresserImage(file)
  const id = newId()
  await photoStore.put(id, blob)
  setState((s) => ({ photos: [...s.photos, { id, target, ref }] }))
  requestSync()
}

export async function retirerPhoto(id) {
  await photoStore.delete(id).catch(() => {})
  setState((s) => ({ photos: s.photos.filter((p) => p.id !== id) }))
}

export async function retirerPhotosDe(target, ref) {
  for (const p of state.photos.filter((x) => x.target === target && x.ref === ref)) await retirerPhoto(p.id)
}

/** Photos d'un journal ou d'un incident : celles d'Odoo, puis celles qui
 *  attendent d'être envoyées. */
export function photosDe(s, target, ref, serverPhotos = []) {
  return [
    ...serverPhotos.map((p) => ({ key: `srv-${p.id}`, serverId: p.id })),
    ...s.photos.filter((p) => p.target === target && p.ref === ref).map((p) => ({ key: p.id, localId: p.id })),
  ]
}

export async function photoBlob(photo) {
  if (photo.localId) return photoStore.get(photo.localId)
  const cached = await photoStore.get(photo.key)
  if (cached) return cached
  const blob = await api.photo(state.session, photo.serverId)
  photoStore.put(photo.key, blob).catch(() => {})
  return blob
}

/* ---------- Synchronisation ----------
 * 1. envoyer les saisies : en-têtes de journal, puis travaux, puis
 *    incidents (une opération chacun) ;
 * 2. envoyer les photos dont le journal ou l'incident existe dans Odoo ;
 * 3. recharger les données d'Odoo. */

let timer
let courante = null
let relancer = false

export function requestSync(delay = 2000) {
  clearTimeout(timer)
  timer = setTimeout(sync, delay)
}

export function sync() {
  if (courante) {
    relancer = true
    return courante
  }
  courante = executer().finally(() => {
    courante = null
    if (relancer) {
      relancer = false
      requestSync(0)
    }
  })
  return courante
}

async function executer() {
  const session = state.session
  if (!session?.token) return
  setState(() => ({ syncing: true }))
  try {
    await envoyerSaisies(session)
    await envoyerPhotos(session)
    const snapshot = await api.pull(session)
    setState(() => ({ snapshot, pulledAt: new Date().toISOString(), online: true, syncError: null }))
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    if (e.status === 401) {
      setState((s) => ({ session: { ...s.session, token: null } }))
    }
    setState(() => ({ online: e.status !== 0, syncError: e.status === 0 ? null : e.message }))
  } finally {
    setState(() => ({ syncing: false }))
  }
}

const OPS = {
  journals: (l) => ({
    uuid: l.uuid, kind: 'journal.header', base_version: l.base_version, submit: l.submit,
    data: { project_id: l.project_id, date: l.date, ...l.data },
  }),
  works: (l) => (l.deleted
    ? { uuid: l.uuid, kind: 'work.delete', base_version: l.base_version,
        data: { project_id: l.project_id, date: l.date, uid: l.uid } }
    : { uuid: l.uuid, kind: 'work.upsert', base_version: l.base_version, validate: l.validate,
        data: { project_id: l.project_id, date: l.date, uid: l.uid, ...l.data } }),
  incidents: (l) => (l.id
    ? { uuid: l.uuid, kind: 'incident.update', id: l.id, base_version: l.base_version, data: l.data }
    : { uuid: l.uuid, kind: 'incident.create', data: { task_id: l.task_id, ...l.data } }),
}

async function envoyerSaisies(session) {
  const refs = {}
  const ops = []
  const pending = (table) => Object.values(state[table]).filter((l) => l.status === 'pending')
  // Les en-têtes d'abord (ils créent le journal), puis les travaux ; un
  // en-tête qui soumet passe après : Odoo refuse de soumettre un journal vide.
  const ordre = [
    ['journals', pending('journals').filter((l) => !l.submit)],
    ['works', pending('works').sort((a, b) => a.created - b.created)],
    ['journals', pending('journals').filter((l) => l.submit)],
    ['incidents', pending('incidents')],
  ]
  for (const [table, list] of ordre) {
    for (const l of list) {
      ops.push(OPS[table](l))
      refs[l.uuid] = [table, table === 'works' ? l.uid : l.key]
    }
  }
  if (!ops.length) return
  const { results } = await api.push(session, ops)
  setState((s) => {
    let next = {
      journals: { ...s.journals }, works: { ...s.works }, incidents: { ...s.incidents },
      snapshot: s.snapshot, photos: s.photos,
    }
    for (const r of results) {
      if (refs[r.uuid]) next = appliquer(next, r, ...refs[r.uuid])
    }
    return next
  })
}

/** Réponse d'Odoo à une opération. La saisie locale n'est effacée que si
 *  elle n'a pas changé pendant l'envoi (même uuid) ; sinon elle repart au
 *  prochain envoi, sur la nouvelle version du serveur. */
function appliquer(s, r, table, key) {
  const local = s[table][key]
  if (!local) return s
  const inchange = local.uuid === r.uuid

  if (r.status === 'conflict') {
    s[table][key] = { ...local, status: 'conflict', conflict: { reason: r.reason, message: r.message, record: r.record } }
    return s
  }
  if (r.status === 'error') {
    if (inchange) s[table][key] = { ...local, status: 'error', error: r.message }
    return s
  }

  if (r.record) s.snapshot = withRecord(s.snapshot, recordTable(table), r.record)
  if (table !== 'incidents') {
    if (inchange || local.deleted) delete s[table][key]
    else s[table][key] = { ...local, base_version: versionDe(table, local, r.record) }
    return s
  }

  // Incident : un incident créé sur le téléphone prend son id Odoo
  const serverKey = `s-${r.record.id}`
  delete s.incidents[key]
  if (key !== serverKey) {
    s.photos = s.photos.map((p) => (p.target === 'incident' && p.ref === key ? { ...p, ref: serverKey } : p))
  }
  const resteAEnvoyer = !inchange || (!local.id && local.data.etat && local.data.etat !== r.record.etat)
  if (resteAEnvoyer) {
    s.incidents[serverKey] = {
      ...local, key: serverKey, id: r.record.id, base_version: r.record.version,
      data: inchange ? { etat: local.data.etat } : local.data,
      uuid: inchange ? newId() : local.uuid,
    }
  }
  return s
}

function withRecord(snapshot, table, record) {
  if (!snapshot) return snapshot
  const list = snapshot[table]
  const exists = list.some((x) => x.id === record.id)
  return { ...snapshot, [table]: exists ? list.map((x) => (x.id === record.id ? record : x)) : [...list, record] }
}

async function envoyerPhotos(session) {
  for (const p of state.photos) {
    const resId = p.target === 'journal'
      ? serverJournalByKey(state, p.ref)?.id
      : p.ref.startsWith('s-') ? Number(p.ref.slice(2)) : null
    if (!resId) continue
    const blob = await photoStore.get(p.id)
    if (blob) {
      try {
        const res = await api.uploadPhoto(session, { uuid: p.id, model: p.target, resId, blob })
        await photoStore.put(`srv-${res.id}`, blob)
      } catch (e) {
        if (e.status === 0 || e.status === 401) throw e
        continue // refusée (chantier clos...) : on réessaiera, elle reste visible
      }
    }
    await photoStore.delete(p.id).catch(() => {})
    setState((s) => ({ photos: s.photos.filter((x) => x.id !== p.id) }))
  }
}
