import { useState } from 'react'
import {
  METEO_ICONES, addDays, dateCourte, incidentsView, jourRelatif, journalStatut, nombre,
  projectJournals, today,
} from '../store.js'
import Incidents from './Incidents.jsx'
import { Badge, Empty, Field, Icon, Modal, Ring, Tile, Ticks, TopBar } from './ui.jsx'

const ONGLETS = [
  ['journaux', 'Journaux'],
  ['phases', 'Phases'],
  ['incidents', 'Incidents'],
]

export default function ChantierDetail({ app, project, route, navigate, back }) {
  const onglet = route.tab ?? 'journaux'
  const setOnglet = (tab) => navigate({ ...route, tab, incident: undefined }, { replace: true })
  const incidents = incidentsView(app, project.id).filter((i) => i.etat !== 'resolu').length
  const phases = app.snapshot.phases.filter((p) => p.project_id === project.id)
  const finies = phases.filter((p) => p.progress >= 100)
  const enRetard = phases.filter((p) => p.progress < 100 && p.deadline && p.deadline < today())
  const enCours = phases.filter((p) => p.progress > 0 && p.progress < 100)
  const reste = phases.length - finies.length - enRetard.length
  const ville = project.address?.split(',').at(-1)?.trim()
  const hauteur = (n) => `${Math.max(46, (n / Math.max(1, phases.length)) * 100)}%`

  return (
    <>
      <TopBar title={project.name} onBack={back}
        right={project.address
          ? <a className="tile" aria-label="Itinéraire" target="_blank" rel="noreferrer"
              href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(project.address)}`}>
              <Icon name="pin" />
            </a>
          : <span />} />

      <div className="chips">
        <span className="chip chip-tile"><span className="tile tile-soft"><Icon name="building" size={18} /></span>{ville ?? 'Chantier'}</span>
        <span className="chip chip-tile"><span className="tile tile-soft"><Icon name="calendar" size={18} /></span>{dateCourte(project.date_end)}</span>
      </div>

      <div className="site-mini">
        <div className="mini mini-accent">
          <span className="mini-title">Avancement</span>
          <span className="mini-value">{nombre(project.progress, 0)}%</span>
          <span className="mini-sub">depuis le {dateCourte(project.date_start)}</span>
        </div>
        <div className="mini">
          <span className="mini-title">Phases en cours</span>
          <span className="mini-value">{enCours.length}</span>
          <span className="mini-sub">sur {phases.length}</span>
        </div>
      </div>

      <section className="card">
        <div className="card-head">
          <Tile icon="layers" label="Phases" tone="tile-soft" />
          <h2 className="grow card-title">Phases du chantier</h2>
          <Tile icon="arrow" label="Voir les phases" onClick={() => setOnglet('phases')} />
        </div>
        <div className="bars-wrap">
          <div className="bars">
            <div className="bar bar-a" style={{ height: hauteur(finies.length) }}>
              <div><strong>{finies.length}</strong><br /><span>Finies</span></div>
              <em>{nombre((100 * finies.length) / Math.max(1, phases.length), 0)} %</em>
            </div>
            <div className="bar bar-b" style={{ height: hauteur(enRetard.length) }}>
              <div><strong>{enRetard.length}</strong><br /><span>En retard</span></div>
              <em>à rattraper</em>
            </div>
            <div className="bar bar-c" style={{ height: hauteur(reste) }}>
              <div><strong>{reste}</strong><br /><span>À venir</span></div>
              <em>{dateCourte(project.date_end)}</em>
            </div>
          </div>
        </div>
        <div style={{ marginTop: 14 }}><Ticks value={project.progress} /></div>
      </section>

      <div className="tabs" role="tablist">
        {ONGLETS.map(([key, text]) => (
          <button type="button" key={key} role="tab" aria-selected={onglet === key}
            className={onglet === key ? 'active' : ''} onClick={() => setOnglet(key)}>
            {text}
            {key === 'incidents' && incidents > 0 && <span className="tab-count">{incidents}</span>}
          </button>
        ))}
      </div>

      {onglet === 'journaux' && <Journaux app={app} project={project} navigate={navigate} />}
      {onglet === 'phases' && <Phases phases={phases} />}
      {onglet === 'incidents' && <Incidents app={app} project={project} ouvert={route.incident} />}
    </>
  )
}

function Journaux({ app, project, navigate }) {
  const [autreDate, setAutreDate] = useState(false)
  const journaux = projectJournals(app, project.id)
  const ouvrir = (date) => navigate({ name: 'journal', projectId: project.id, date })
  const aujourdhui = journaux.find((j) => j.date === today())

  return (
    <section className="list">
      <div className="btn-row">
        <button type="button" className="btn btn-primary grow" onClick={() => ouvrir(today())}>
          <Icon name="book" size={18} />
          {aujourdhui ? "Journal d'aujourd'hui" : 'Commencer le journal du jour'}
        </button>
        <Tile icon="calendar" label="Journal d'un autre jour" onClick={() => setAutreDate(true)} />
      </div>

      {journaux.length === 0 && <Empty>Aucun journal sur les 30 derniers jours.</Empty>}

      {journaux.map((j) => {
        const statut = journalStatut(app, j)
        const valides = j.works.filter((w) => w.server?.state === 'validated').length
        const ouvriers = new Set(j.works.flatMap((w) => w.data.labor.map((l) => l.employee_id))).size
        return (
          <button type="button" key={j.date} className="list-row" onClick={() => ouvrir(j.date)}>
            <span className="tile tile-soft" style={{ fontSize: 22 }}>{METEO_ICONES[j.header.weather] ?? '·'}</span>
            <div className="row-main">
              <strong className="capitalize">{jourRelatif(j.date)}</strong>
              <span>
                {j.works.length} ligne{j.works.length > 1 ? 's' : ''} · {valides} validée{valides > 1 ? 's' : ''} · {ouvriers} ouvrier{ouvriers > 1 ? 's' : ''}
              </span>
            </div>
            {statut && <Badge tone={statut.tone}>{statut.label}</Badge>}
          </button>
        )
      })}

      {autreDate && (
        <Modal title="Journal d'un autre jour" onClose={() => setAutreDate(false)}>
          <AutreDate onSubmit={(d) => { setAutreDate(false); ouvrir(d) }} />
        </Modal>
      )}
    </section>
  )
}

function AutreDate({ onSubmit }) {
  const [date, setDate] = useState(addDays(today(), -1))
  return (
    <form className="form" onSubmit={(e) => { e.preventDefault(); onSubmit(date) }}>
      <Field label="Date">
        <input type="date" required max={today()} value={date} onChange={(e) => setDate(e.target.value)} />
      </Field>
      <button type="submit" className="btn btn-primary">Ouvrir</button>
    </form>
  )
}

const FILTRES = [
  ['encours', 'En cours', (p) => p.progress > 0 && p.progress < 100],
  ['afaire', 'À faire', (p) => p.progress === 0],
  ['finies', 'Finies', (p) => p.progress >= 100],
  ['toutes', 'Toutes', () => true],
]

function Phases({ phases }) {
  const [filtre, setFiltre] = useState('encours')
  const [recherche, setRecherche] = useState('')
  const visibles = filtrerPhases(phases, recherche, FILTRES.find(([k]) => k === filtre)[2])

  return (
    <section className="list">
      <Recherche value={recherche} onChange={setRecherche} placeholder="Rechercher une phase…" />
      <div className="chips">
        {FILTRES.map(([key, text, fn]) => (
          <button type="button" key={key} className={`chip ${filtre === key ? 'active' : ''}`}
            onClick={() => setFiltre(key)}>
            {text} {phases.filter(fn).length}
          </button>
        ))}
      </div>
      <ListePhases phases={visibles} renderRow={(p) => (
        <div key={p.id} className="list-row">
          <span className="tile tile-soft"><Icon name="layers" size={18} /></span>
          <div className="row-main">
            <strong>{p.name}</strong>
            <span>
              {p.qty > 0 ? `${nombre(p.qty_done)} / ${nombre(p.qty)} ${p.unit ?? ''}` : 'Sans métré'}
              {p.deadline && ` · ${dateCourte(p.deadline)}`}
            </span>
          </div>
          <Ring value={p.progress} />
        </div>
      )} />
    </section>
  )
}

export function Recherche({ value, onChange, placeholder }) {
  return (
    <div className="search">
      <Icon name="search" size={18} />
      <input type="search" placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
      {value && <Tile icon="close" label="Effacer" tone="tile-soft" size={16} onClick={() => onChange('')} />}
    </div>
  )
}

const LIMITE = 150

export function filtrerPhases(phases, recherche, filtre = () => true) {
  const q = recherche.trim().toLowerCase()
  return phases.filter((p) => filtre(p) && (!q || `${p.path ?? ''} ${p.name}`.toLowerCase().includes(q)))
}

/** Phases regroupées par ouvrage (le chemin de la tâche mère). Au-delà de
 *  LIMITE lignes, on demande d'affiner plutôt que de tout afficher. */
export function ListePhases({ phases, renderRow }) {
  if (phases.length === 0) return <Empty>Aucune phase.</Empty>
  const groupes = new Map()
  for (const p of phases.slice(0, LIMITE)) {
    const g = p.path ?? 'Sans ouvrage'
    if (!groupes.has(g)) groupes.set(g, [])
    groupes.get(g).push(p)
  }
  return (
    <>
      {[...groupes].map(([groupe, list]) => (
        <div key={groupe} className="list">
          <h3 className="group-title">{groupe}</h3>
          {list.map(renderRow)}
        </div>
      ))}
      {phases.length > LIMITE && (
        <p className="muted small center">{phases.length - LIMITE} autres phases : affinez la recherche.</p>
      )}
    </>
  )
}
