import { useState } from 'react'
import {
  creerIncident, dateCourte, incidentsView, journalView, label, modifierIncident,
  nouvelleCleIncident, resoudre, retirerPhotosDe, today,
} from '../store.js'
import Photos from './Photos.jsx'
import { PhasePicker } from './Pickers.jsx'
import { Badge, Banner, Empty, Field, Icon, Modal, Segmented } from './ui.jsx'

const GRAVITE_TONS = { faible: 'info', moyenne: 'warn', haute: 'accent', critique: 'danger' }
const ETAT_TONS = { ouvert: 'danger', en_cours: 'warn', resolu: 'success' }

/** Incidents d'un chantier, ou de tous les chantiers si `project` est vide. */
export default function Incidents({ app, project, ouvert }) {
  const [filtre, setFiltre] = useState('ouverts')
  const [nouveau, setNouveau] = useState(false)
  const [detail, setDetail] = useState(ouvert ?? null)
  const sel = app.snapshot.selections
  const tous = incidentsView(app, project?.id)
  const visibles = tous.filter((i) => (filtre === 'ouverts' ? i.etat !== 'resolu' : true))
  const incident = tous.find((i) => i.key === detail)
  const phase = (id) => app.snapshot.phases.find((p) => p.id === id)
  const projet = (id) => app.snapshot.projects.find((p) => p.id === id)

  return (
    <section className="list">
      {project && (
        <button type="button" className="btn btn-primary btn-block" onClick={() => setNouveau(true)}>
          <Icon name="flag" size={18} /> Signaler un incident
        </button>
      )}

      <div className="chips">
        {[['ouverts', 'Non résolus'], ['tous', 'Tous (30 j)']].map(([key, text]) => (
          <button type="button" key={key} className={`chip ${filtre === key ? 'active' : ''}`}
            onClick={() => setFiltre(key)}>
            {text}
          </button>
        ))}
      </div>

      {visibles.length === 0 && <Empty>Aucun incident.</Empty>}

      {visibles.map((i) => (
            <button type="button" key={i.key} className="list-row" onClick={() => setDetail(i.key)}>
              <span className={`tile tile-soft`} style={{ color: `var(--${GRAVITE_TONS[i.gravite]})` }}>
                <Icon name="flag" size={18} />
              </span>
              <div className="row-main">
                <strong>{i.name}</strong>
                <span>
                  {!project && `${projet(i.project_id)?.name} · `}
                  {phase(i.task_id)?.name ?? 'Phase'} · {dateCourte(i.date)}
                </span>
              </div>
              <div className="row-end">
                <Badge tone={ETAT_TONS[i.etat]}>{label(sel.incident_etat, i.etat)}</Badge>
                {i.local && (
                  <span className={`small ${i.local.status === 'pending' ? 'muted' : 'date-late'}`}>
                    {i.local.status === 'pending' ? 'Non envoyé' : i.local.status === 'conflict' ? 'Conflit' : 'Refusé'}
                  </span>
                )}
              </div>
            </button>
      ))}

      {nouveau && (
        <IncidentForm app={app} project={project} onClose={() => setNouveau(false)} />
      )}
      {incident && (
        <IncidentDetail app={app} incident={incident} phase={phase(incident.task_id)} onClose={() => setDetail(null)} />
      )}
    </section>
  )
}

function IncidentForm({ app, project, onClose }) {
  const [key] = useState(nouvelleCleIncident)
  const [phase, setPhase] = useState(null)
  const [choixPhase, setChoixPhase] = useState(false)
  const [values, setValues] = useState({ name: '', gravite: 'moyenne', description: '' })
  const sel = app.snapshot.selections
  const phases = app.snapshot.phases.filter((p) => p.project_id === project.id)
  const duJour = journalView(app, project.id, today()).data?.works.map((w) => w.task_id) ?? []

  const annuler = () => {
    retirerPhotosDe('incident', key)
    onClose()
  }
  const submit = (e) => {
    e.preventDefault()
    creerIncident(project.id, phase.id, {
      name: values.name.trim(), gravite: values.gravite, description: values.description,
    }, key)
    onClose()
  }

  return (
    <Modal title="Signaler un incident" onClose={annuler}>
      <form className="form" onSubmit={submit}>
        <Field label="Phase concernée *">
          <button type="button" className="select-btn" onClick={() => setChoixPhase(true)}>
            {phase ? phase.name : 'Choisir une phase…'}
            <Icon name="down" size={18} />
          </button>
        </Field>
        <Field label="Titre *">
          <input required value={values.name} placeholder="Ex. Fuite sur la canalisation"
            onChange={(e) => setValues((v) => ({ ...v, name: e.target.value }))} />
        </Field>
        <div className="field">
          <span>Gravité</span>
          <Segmented columns={4} value={values.gravite}
            options={sel.incident_gravite.map(([k, l]) => [k, l, <span key={k} className={`dot dot-${GRAVITE_TONS[k]}`} />])}
            onChange={(g) => g && setValues((v) => ({ ...v, gravite: g }))} />
        </div>
        <Field label="Description">
          <textarea rows="3" value={values.description}
            onChange={(e) => setValues((v) => ({ ...v, description: e.target.value }))} />
        </Field>
        <div className="field">
          <span>Photos</span>
          <Photos target="incident" refKey={key} />
        </div>
        <button type="submit" className="btn btn-primary" disabled={!phase || !values.name.trim()}>
          Signaler
        </button>
      </form>
      {choixPhase && (
        <PhasePicker phases={phases} suggestions={duJour} onClose={() => setChoixPhase(false)}
          onPick={(p) => { setPhase(p); setChoixPhase(false) }} />
      )}
    </Modal>
  )
}

function IncidentDetail({ app, incident, phase, onClose }) {
  const sel = app.snapshot.selections
  const local = incident.local
  const [description, setDescription] = useState(incident.description ?? '')

  return (
    <Modal title={incident.name} onClose={onClose}>
      <div className="form">
        {local?.status === 'conflict' && (
          <Banner tone="danger" title="Conflit avec Odoo" actions={
            <>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => resoudre('incidents', incident.key, 'serveur')}>
                Garder la version d'Odoo
              </button>
              {local.conflict.record && (
                <button type="button" className="btn btn-sm btn-primary" onClick={() => resoudre('incidents', incident.key, 'mien')}>
                  Envoyer la mienne
                </button>
              )}
            </>
          }>
            {local.conflict.message}
            {local.conflict.record && ` Dans Odoo : « ${label(sel.incident_etat, local.conflict.record.etat)} ».`}
          </Banner>
        )}
        {local?.status === 'error' && <Banner tone="danger" title="Refusé par Odoo">{local.error}</Banner>}

        <div className="card infos">
          <dl>
            <dt>Phase</dt>
            <dd>{phase?.name ?? '—'}</dd>
            <dt>Date</dt>
            <dd>{dateCourte(incident.date)}</dd>
            <dt>Gravité</dt>
            <dd><Badge tone={GRAVITE_TONS[incident.gravite]}>{label(sel.incident_gravite, incident.gravite)}</Badge></dd>
            {incident.assignee && <><dt>Assigné à</dt><dd>{incident.assignee}</dd></>}
          </dl>
        </div>

        <div className="field">
          <span>État</span>
          <Segmented columns={3} value={incident.etat} options={sel.incident_etat}
            onChange={(etat) => etat && etat !== incident.etat && modifierIncident(incident, { etat })} />
        </div>

        <Field label="Description">
          <textarea rows="3" value={description} onChange={(e) => setDescription(e.target.value)}
            onBlur={() => description !== (incident.description ?? '') && modifierIncident(incident, { description })} />
        </Field>

        <div className="field">
          <span>Photos</span>
          <Photos target="incident" refKey={incident.key} serverPhotos={incident.photos} />
        </div>
      </div>
    </Modal>
  )
}
