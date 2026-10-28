import { useState } from 'react'
import {
  dateCourte, deconnecter, enAttente, formatDate, incidentsView, journalStatut, journalView,
  nombre, sync, today,
} from '../store.js'
import SyncBar from './SyncBar.jsx'
import { Badge, Confirm, Empty, HatchBar, Icon, Modal, Tile, Ticks } from './ui.jsx'

/** Part du temps écoulé entre le début et la fin du chantier (repère
 *  « aujourd'hui » sur la barre). */
function tempsEcoule(debut, fin) {
  if (!debut || !fin) return null
  const t0 = new Date(debut), t1 = new Date(fin), now = new Date(today())
  if (t1 <= t0) return null
  return Math.max(0, Math.min(100, (100 * (now - t0)) / (t1 - t0)))
}

export default function Dashboard({ app, navigate }) {
  const [compte, setCompte] = useState(false)
  const [ask, setAsk] = useState(null)
  const projets = app.snapshot?.projects ?? []
  const moyenne = projets.length ? projets.reduce((s, p) => s + p.progress, 0) / projets.length : 0
  const debut = projets.map((p) => p.date_start).filter(Boolean).sort()[0]
  const fin = projets.map((p) => p.date_end).filter(Boolean).sort().at(-1)
  const ouverts = incidentsView(app).filter((i) => i.etat !== 'resolu').length
  const [entier, decimales] = nombre(moyenne, 2).split(',')
  const initiale = app.session.user?.name?.slice(0, 1).toUpperCase() ?? '?'

  const aTraiter = [
    ...Object.values(app.journals), ...Object.values(app.works),
  ].filter((l) => l.status === 'conflict' || l.status === 'error').map((l) => ({
    key: l.uid ?? l.key,
    titre: `${l.uid ? 'Travail' : 'Journal'} du ${formatDate(l.date, { day: 'numeric', month: 'long' })}`,
    projet: projets.find((p) => p.id === l.project_id)?.name,
    message: l.conflict?.message ?? l.error,
    ouvrir: () => navigate({ name: 'journal', projectId: l.project_id, date: l.date }),
  })).concat(incidentsView(app).filter((i) => i.local && i.local.status !== 'pending').map((i) => ({
    key: i.key,
    titre: `Incident : ${i.name}`,
    projet: projets.find((p) => p.id === i.project_id)?.name,
    message: i.local.conflict?.message ?? i.local.error,
    ouvrir: () => navigate({ name: 'project', id: i.project_id, tab: 'incidents', incident: i.key }),
  })))

  return (
    <>
      <section className="hero">
        <div className="brand">
          <span className="brand-logo"><Icon name="crane" size={24} /></span>
          <span className="brand-name">SuiviChantier</span>
          <Tile icon={app.online ? 'sync' : 'offline'} label="Synchroniser" onClick={() => sync()}
            count={enAttente(app)} />
          <button type="button" className="avatar" aria-label="Mon compte" onClick={() => setCompte(true)}>
            {initiale}
          </button>
        </div>

        <div className="hero-label">
          <p>Avancement de vos chantiers</p>
          <Tile icon="calendar" label={formatDate(today())} tone="tile-soft" />
        </div>
        <div className="big-pct">{entier}{decimales && `,${decimales}`}<small>%</small></div>

        <div className="hero-meta">
          <div>Fin prévue<strong>{fin ? dateCourte(fin) : '—'}</strong></div>
          <div style={{ textAlign: 'right' }}>
            Incidents <strong>{ouverts} <em>ouvert{ouverts > 1 ? 's' : ''}</em></strong>
          </div>
        </div>
        <HatchBar value={moyenne} mark={tempsEcoule(debut, fin)} />
        <SyncBar app={app} />
      </section>

      {aTraiter.length > 0 && (
        <section className="card card-alert">
          <div className="card-head">
            <Tile icon="alert" label="À traiter" tone="tile-danger" />
            <h2 className="grow">À traiter</h2>
          </div>
          <div className="list" style={{ marginTop: 12 }}>
            {aTraiter.map((t) => (
              <button type="button" key={t.key} className="list-row" onClick={t.ouvrir}>
                <div className="row-main">
                  <strong>{t.titre}</strong>
                  <span>{t.projet}</span>
                  <span className="date-late">{t.message}</span>
                </div>
                <Icon name="chevron" />
              </button>
            ))}
          </div>
        </section>
      )}

      {!app.snapshot && (
        <section className="card">
          <Empty>{app.syncing ? 'Chargement des chantiers…' : 'Aucune donnée : synchronisez avec le réseau.'}</Empty>
        </section>
      )}
      {app.snapshot && projets.length === 0 && (
        <section className="card"><Empty>Aucun chantier en cours ne vous est attribué dans Odoo.</Empty></section>
      )}

      {projets.length > 0 && <div className="section-head"><h2>Mes chantiers</h2><span className="muted small">{projets.length}</span></div>}

      <div className="cards">
        {projets.map((p) => (
          <CarteChantier key={p.id} app={app} projet={p} navigate={navigate} />
        ))}
      </div>

      {compte && (
        <Modal title="Mon compte" onClose={() => setCompte(false)}>
          <div className="card infos">
            <dl>
              <dt>Utilisateur</dt>
              <dd>{app.session.user?.name}</dd>
              <dt>Identifiant</dt>
              <dd>{app.session.login}</dd>
              <dt>Serveur</dt>
              <dd>{app.session.url}</dd>
              <dt>En attente</dt>
              <dd>{enAttente(app)} saisie(s)</dd>
            </dl>
          </div>
          <button type="button" className="btn btn-danger" onClick={() => {
            const n = enAttente(app)
            setAsk({
              title: 'Se déconnecter ?',
              text: n ? `${n} saisie(s) n'ont pas encore été envoyées et seront perdues.` : 'Il faudra se reconnecter pour saisir des journaux.',
              ok: 'Se déconnecter', danger: true,
              onOk: () => { setCompte(false); deconnecter() },
            })
          }}>
            <Icon name="logout" size={18} /> Se déconnecter
          </button>
        </Modal>
      )}
      <Confirm ask={ask} onClose={() => setAsk(null)} />
    </>
  )
}

function CarteChantier({ app, projet: p, navigate }) {
  const vue = journalView(app, p.id, today())
  const statut = journalStatut(app, vue)
  const incidents = incidentsView(app, p.id).filter((i) => i.etat !== 'resolu').length
  const phases = app.snapshot.phases.filter((ph) => ph.project_id === p.id)
  const finies = phases.filter((ph) => ph.progress >= 100).length
  const ouvrir = () => navigate({ name: 'project', id: p.id })
  const journal = () => navigate({ name: 'journal', projectId: p.id, date: today() })

  return (
    <article className="card site-card">
      <div className="card-head">
        <Tile icon="building" label={p.name} tone="tile-soft" onClick={ouvrir} />
        <button type="button" className="grow" style={{ border: 0, background: 'none', padding: 0, textAlign: 'left' }} onClick={ouvrir}>
          <h2 style={{ fontSize: 17, fontWeight: 650 }}>{p.name}</h2>
          {p.address && <span className="muted small with-icon"><Icon name="pin" size={13} /> {p.address}</span>}
        </button>
        <Tile icon="arrow" label="Ouvrir le chantier" onClick={ouvrir} />
      </div>

      <div className="site-visual">
        <div className="site-visual-top">
          <div>
            <span className="muted small">Avancement</span>
            <div className="big-pct">{nombre(p.progress, 1)}<small>%</small></div>
          </div>
          <div className="ticks-labels" style={{ gap: 18 }}>
            <span>Phases<strong>{finies}/{phases.length}</strong></span>
            <span>Fin<strong>{dateCourte(p.date_end)}</strong></span>
          </div>
        </div>
        <Ticks value={p.progress} />
      </div>

      <div className="site-mini">
        <button type="button" className="mini mini-accent" onClick={journal}>
          <span className="mini-title">Journal du jour</span>
          <span className="mini-sub">{statut ? '' : 'Pas encore commencé'}</span>
          {statut && <Badge tone={statut.tone}>{statut.label}</Badge>}
          <span className="mini-value">{vue.works.length}<span className="mini-sub"> ligne{vue.works.length > 1 ? 's' : ''}</span></span>
          <span className="tile tile-grad"><Icon name="plus" size={18} /></span>
        </button>
        <button type="button" className="mini" onClick={() => navigate({ name: 'project', id: p.id, tab: 'incidents' })}>
          <span className="mini-title">Incidents</span>
          <span className="mini-sub">non résolus</span>
          <span className="mini-value" style={incidents ? { color: 'var(--danger)' } : undefined}>{incidents}</span>
          <span className="tile"><Icon name="arrow" size={18} /></span>
        </button>
      </div>
    </article>
  )
}
