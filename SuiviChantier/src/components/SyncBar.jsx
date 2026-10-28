import { enAttente, sync } from '../store.js'
import { Icon } from './ui.jsx'

function depuis(iso) {
  if (!iso) return 'jamais'
  const min = Math.round((Date.now() - new Date(iso)) / 60000)
  if (min < 1) return "à l'instant"
  if (min < 60) return `il y a ${min} min`
  const h = Math.round(min / 60)
  return h < 24 ? `il y a ${h} h` : new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

export function syncEtat(app) {
  const attente = enAttente(app)
  const s = attente > 1 ? 's' : ''
  if (app.syncing) return { tone: 'info', icon: 'sync', texte: 'Synchronisation…' }
  if (!app.online) {
    return {
      tone: 'warn', icon: 'offline',
      texte: attente ? `Hors-ligne · ${attente} saisie${s} en attente` : 'Hors-ligne · tout est sur le téléphone',
    }
  }
  if (app.syncError) return { tone: 'danger', icon: 'alert', texte: app.syncError }
  if (attente) return { tone: 'warn', icon: 'sync', texte: `${attente} saisie${s} en attente d'envoi` }
  return { tone: 'success', icon: 'check', texte: `À jour · ${depuis(app.pulledAt)}` }
}

/** État de la synchronisation : le chef de chantier sait si ses saisies
 *  sont parties. Un appui relance l'envoi. */
export default function SyncBar({ app }) {
  const { tone, icon, texte } = syncEtat(app)
  return (
    <button type="button" className={`syncpill syncpill-${tone} ${app.syncing ? 'spinning' : ''}`}
      onClick={() => sync()} disabled={app.syncing}>
      <Icon name={icon} size={16} />
      <span>{texte}</span>
    </button>
  )
}
