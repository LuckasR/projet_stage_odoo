import { useEffect, useState } from 'react'
import {
  METEO_ICONES, abandonner, argent, dateCourte, etatLigne, jourRelatif, journalStatut, journalView,
  label, newId, nombre, nouveauTravail, projectJournals, requestSync, resoudre, saveHeader, saveWork,
  supprimerWork,
} from '../store.js'
import Photos from './Photos.jsx'
import { EmployeePicker, EquipmentPicker, PhasePicker } from './Pickers.jsx'
import {
  Badge, Banner, Confirm, Empty, Icon, Ring, Segmented, Stepper, Tile, TopBar,
} from './ui.jsx'

// Avancement d'une phase sans métré, comme dans Odoo
const STATUS_PROGRESS = { todo: 0, doing: 50, done: 100 }

const etatDe = (l) => etatLigne(l.state, l.validate)

/** Les lignes d'un journal se valident une à une, au fil de la journée :
 *  une ligne validée est figée et compte aussitôt dans Odoo (stock,
 *  avancement, coûts). On ajoute des lignes tant que le conducteur n'a pas
 *  validé le journal entier. */
export default function JournalEditor({ app, projectId, date, back }) {
  const snap = app.snapshot
  const project = snap.projects.find((p) => p.id === projectId)
  const phases = snap.phases.filter((p) => p.project_id === projectId)
  const phaseDe = (id) => phases.find((p) => p.id === id)
  const vue = journalView(app, projectId, date)
  const journalValide = vue.state === 'validated'
  const [choixPhase, setChoixPhase] = useState(false)
  const [ask, setAsk] = useState(null)

  // Partir de la dernière version d'Odoo évite des conflits inutiles
  useEffect(() => { requestSync(0) }, [])

  const updateHeader = (fn) => {
    const d = structuredClone(vue.header)
    fn(d)
    saveHeader(projectId, date, d)
  }
  const ajouterLigne = (taskId) => saveWork(projectId, date, newId(), nouveauTravail(taskId))

  const precedent = projectJournals(app, projectId).find((j) => j.date < date)
  const reprendre = () => {
    for (const w of precedent.works) {
      const phase = phaseDe(w.data.task_id)
      if (!phase || phase.progress >= 100 || vue.works.some((x) => x.data.task_id === w.data.task_id)) continue
      saveWork(projectId, date, newId(), {
        ...nouveauTravail(w.data.task_id),
        status: w.data.status,
        labor: w.data.labor.map((l) => ({ uid: newId(), employee_id: l.employee_id, hours: l.hours })),
        equipment: w.data.equipment.map((l) => ({ uid: newId(), equipment_id: l.equipment_id, hours: l.hours })),
      })
    }
  }

  const statut = journalStatut(app, vue)
  const conflit = vue.local?.status === 'conflict' ? vue.local.conflict : null
  const soumis = vue.state === 'submitted' || vue.local?.submit
  const vide = !vue.works.length && !vue.header.site_equipment.length && !vue.header.site_expenses.length && !vue.header.hours_lost
  const valides = vue.works.filter((w) => etatDe({ state: w.server?.state, validate: w.local?.validate }) !== 'draft').length
  const heures = vue.works.flatMap((w) => w.data.labor).reduce((s, l) => s + (Number(l.hours) || 0), 0)
  const dejaDuJour = vue.works.reduce((acc, w) => ({ ...acc, [w.data.task_id]: (acc[w.data.task_id] ?? 0) + 1 }), {})

  return (
    <>
      <TopBar title={jourRelatif(date)} subtitle={project?.name} onBack={back}
        right={<Tile icon="calendar" label={dateCourte(date)} tone="tile-soft" />} />

      <section className="card">
        <div className="card-head">
          <span className="chip chip-tile" style={{ boxShadow: 'none' }}>
            <span className="tile tile-soft"><Icon name="calendar" size={18} /></span>{dateCourte(date)}
          </span>
          <span className="grow" />
          {statut && <Badge tone={statut.tone}>{statut.label}</Badge>}
        </div>
        <div className="site-mini" style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginTop: 14 }}>
          <Chiffre titre="Lignes" valeur={vue.works.length} />
          <Chiffre titre="Validées" valeur={valides} accent />
          <Chiffre titre="Heures" valeur={nombre(heures, 1)} />
        </div>
      </section>

      {conflit && (
        <Banner tone="danger" title="Conflit avec Odoo" actions={
          <>
            {conflit.reason !== 'deleted' && (
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => resoudre('journals', vue.key, 'serveur')}>
                Garder la version d'Odoo
              </button>
            )}
            {conflit.reason !== 'locked' && (
              <button type="button" className="btn btn-sm btn-primary" onClick={() => resoudre('journals', vue.key, 'mien')}>
                {conflit.reason === 'deleted' ? 'Recréer le journal' : 'Envoyer ma version'}
              </button>
            )}
          </>
        }>
          {conflit.message} (météo, observations, frais du chantier)
        </Banner>
      )}
      {vue.local?.status === 'error' && (
        <Banner tone="danger" title="Refusé par Odoo">{vue.local.error} Corrigez : la saisie repartira d'elle-même.</Banner>
      )}
      {journalValide && (
        <Banner tone="success" icon="lock" title="Journal validé">
          Le conducteur de travaux l'a validé : plus rien ne peut être modifié.
        </Banner>
      )}
      {!journalValide && soumis && (
        <Banner tone="info" icon="send" title={vue.state === 'submitted' ? 'Soumis au conducteur' : 'Soumission en attente'}>
          Vous pouvez encore ajouter et valider des lignes jusqu'à la validation du journal.
        </Banner>
      )}

      <section className="card">
        <h2 className="card-title">Météo</h2>
        <div style={{ marginTop: 12 }}>
          <Segmented columns={4} value={vue.header.weather} disabled={journalValide}
            options={snap.selections.weather.map(([k, l]) => [k, l, METEO_ICONES[k]])}
            onChange={(w) => updateHeader((d) => { d.weather = w })} />
        </div>
        <div className="inline-field">
          <div>
            <strong>Heures d'arrêt</strong>
            <p className="muted small">Intempéries, attente de livraison, panne…</p>
          </div>
          <Stepper value={vue.header.hours_lost} step={0.5} unit="h" label="Heures d'arrêt" readOnly={journalValide}
            onChange={(v) => updateHeader((d) => { d.hours_lost = v })} />
        </div>
      </section>

      <div className="section-head">
        <h2>Travaux du jour</h2>
        <span className="muted small">{vue.works.length} ligne{vue.works.length > 1 ? 's' : ''}</span>
      </div>

      {!journalValide && vue.works.length === 0 && precedent?.works.length > 0 && (
        <button type="button" className="card suggestion" onClick={reprendre}>
          <span className="tile tile-grad"><Icon name="copy" size={18} /></span>
          <div className="row-main">
            <strong>Reprendre le journal {precedent.date === date ? '' : `du ${dateCourte(precedent.date)}`}</strong>
            <span className="muted small">Mêmes phases, équipe et matériel ; il ne reste qu'à saisir le réalisé.</span>
          </div>
        </button>
      )}
      {vue.works.length === 0 && journalValide && <Empty>Aucun travail déclaré.</Empty>}

      {vue.works.map((w) => (
        <WorkCard key={w.uid} app={app} vue={vue} work={w} phase={phaseDe(w.data.task_id)}
          journalValide={journalValide} setAsk={setAsk} ajouterLigne={ajouterLigne} />
      ))}

      {!journalValide && (
        <button type="button" className="btn btn-dashed btn-block" onClick={() => setChoixPhase(true)}>
          <Icon name="plus" size={18} /> Ajouter une ligne
        </button>
      )}

      <Repliable titre="Frais du chantier" resume={resumeFrais(vue.header, app)} forceOpen={journalValide}
        aide="Matériel et dépenses qui ne concernent pas une phase précise (gardiennage, engin pour tout le chantier…).">
        <MaterielLignes app={app} lignes={vue.header.site_equipment} fige={journalValide} setAsk={setAsk}
          change={(fn) => updateHeader((d) => fn(d.site_equipment))} />
        <DepenseLignes app={app} lignes={vue.header.site_expenses} fige={journalValide} setAsk={setAsk}
          change={(fn) => updateHeader((d) => fn(d.site_expenses))} />
      </Repliable>

      <section className="card">
        <h2 className="card-title">Observations</h2>
        <textarea className="textarea" rows="4" value={vue.header.notes ?? ''} readOnly={journalValide}
          style={{ marginTop: 10 }}
          placeholder="Livraisons, visites, réserves, incidents de la journée…"
          onChange={(e) => updateHeader((d) => { d.notes = e.target.value })} />
      </section>

      <section className="card">
        <h2 className="card-title">Photos</h2>
        <Photos target="journal" refKey={vue.key} serverPhotos={vue.server?.photos} editable={!journalValide} />
      </section>

      {!journalValide && (
        <div className="action-bar">
          <span className="action-bar-status">
            {vue.saisies.length ? (app.online ? 'Enregistré · envoi automatique' : 'Enregistré sur le téléphone')
              : vue.server ? 'Synchronisé avec Odoo' : 'Enregistrement automatique'}
          </span>
          {!soumis && (
            <button type="button" className="btn btn-primary" disabled={vide}
              onClick={() => setAsk({
                title: 'Soumettre le journal ?',
                text: "Le conducteur de travaux est prévenu que la journée est finie. Vous pourrez encore ajouter et valider des lignes jusqu'à ce qu'il valide le journal.",
                ok: 'Soumettre',
                onOk: () => saveHeader(projectId, date, vue.header, { submit: true }),
              })}>
              <Icon name="send" size={18} /> Soumettre
            </button>
          )}
        </div>
      )}

      {choixPhase && (
        <PhasePicker phases={phases} dejaDuJour={dejaDuJour}
          suggestions={precedent?.works.map((w) => w.data.task_id)}
          onClose={() => setChoixPhase(false)}
          onPick={(p) => { setChoixPhase(false); ajouterLigne(p.id) }} />
      )}
      <Confirm ask={ask} onClose={() => setAsk(null)} />
    </>
  )
}

function Chiffre({ titre, valeur, accent }) {
  return (
    <div className={`mini ${accent ? 'mini-accent' : ''}`} style={{ minHeight: 0, padding: 12 }}>
      <span className="mini-sub">{titre}</span>
      <span className="mini-value" style={{ fontSize: 24 }}>{valeur}</span>
    </div>
  )
}

function resumeFrais(header, app) {
  const total = header.site_expenses.reduce((s, e) => s + (Number(e.amount) || 0), 0)
  const parts = []
  if (header.site_equipment.length) parts.push(`${header.site_equipment.length} matériel`)
  if (total) parts.push(argent(total, app.snapshot.currency))
  return parts.join(' · ') || 'Aucun'
}

function Repliable({ titre, resume, aide, forceOpen, children }) {
  const [deplie, setDeplie] = useState(false)
  const ouvert = forceOpen || deplie
  return (
    <section className="card">
      <button type="button" className="repliable-head" onClick={() => setDeplie((o) => !o)} aria-expanded={ouvert}>
        <span className="tile tile-soft tile-sm"><Icon name="crane" size={18} /></span>
        <h2>{titre}</h2>
        <span className="muted small">{resume}</span>
        <span className={`chevron ${ouvert ? 'open' : ''}`}><Icon name="down" size={18} /></span>
      </button>
      {ouvert && (
        <div className="repliable-body">
          {aide && <p className="muted small">{aide}</p>}
          {children}
        </div>
      )}
    </section>
  )
}

/** Coche de validation d'une ligne : à valider, en attente d'envoi, validée. */
function CheckBtn({ etat, onClick, disabled }) {
  if (etat === 'validated') {
    return <span className="check-btn done" title="Validée"><Icon name="check" size={16} /></span>
  }
  if (etat === 'pending') {
    return <span className="check-btn pending" title="Validation en attente d'envoi"><Icon name="sync" size={15} /></span>
  }
  if (disabled) return null
  return (
    <button type="button" className="check-btn" aria-label="Valider la ligne" title="Valider la ligne" onClick={onClick}>
      <Icon name="check" size={16} />
    </button>
  )
}

const classeLigne = (etat) => `line ${etat === 'validated' ? 'line-validated' : etat === 'pending' ? 'line-pending' : ''}`

function demanderValidation(setAsk, quoi, onOk, extra = '') {
  setAsk({
    title: `Valider ${quoi} ?`,
    text: `Elle sera figée et comptera aussitôt dans Odoo${extra}. Seul le conducteur de travaux pourra l'annuler.`,
    ok: 'Valider',
    onOk,
  })
}

/* ---------- Une ligne de travail (une phase) ---------- */

function verifier(data, phase) {
  const erreurs = []
  if (Number(data.qty_done) < 0 && !data.correction_reason?.trim()) erreurs.push('Indiquez le motif de la correction.')
  if (data.labor.some((l) => !(Number(l.hours) > 0))) erreurs.push("Heures d'ouvrier manquantes.")
  if (data.expenses.some((e) => !e.name?.trim())) erreurs.push('Dépense sans libellé.')
  if (!phase) erreurs.push('Phase introuvable.')
  return erreurs
}

function WorkCard({ app, vue, work, phase, journalValide, setAsk, ajouterLigne }) {
  const snap = app.snapshot
  const { projectId, date } = vue
  const etat = etatLigne(work.server?.state, work.local?.validate)
  const fige = journalValide || etat !== 'draft'
  const [deplie, setDeplie] = useState(etat === 'draft')
  const [choixOuvriers, setChoixOuvriers] = useState(false)
  const conflit = work.local?.status === 'conflict' ? work.local.conflict : null
  const data = work.data
  const change = (fn) => {
    const d = structuredClone(data)
    fn(d)
    saveWork(projectId, date, work.uid, d)
  }
  const employe = (id) => snap.employees.find((e) => e.id === id)
  const qty = Number(data.qty_done) || 0
  const heures = data.labor.reduce((s, l) => s + (Number(l.hours) || 0), 0)
  const erreurs = verifier(data, phase)
  const sousLignes = [...data.labor, ...data.materials, ...data.equipment, ...data.expenses]
  const supprimable = etat === 'draft' && !journalValide && sousLignes.every((l) => etatDe(l) === 'draft')

  const avant = phase?.progress ?? 0
  const apres = etat === 'validated' ? avant
    : phase?.qty ? Math.min(100, Math.max(0, (100 * (phase.qty_done + qty)) / phase.qty))
    : STATUS_PROGRESS[data.status] ?? 0

  const etatBadge = {
    validated: <Badge tone="success"><Icon name="lock" size={12} /> Validé{work.server?.validated_by ? ` · ${work.server.validated_by}` : ''}</Badge>,
    pending: <Badge tone="warn">Validation en attente</Badge>,
    draft: work.local ? <Badge tone="warn">Non envoyé</Badge> : <Badge tone="info">Brouillon</Badge>,
  }[etat]

  // Matières : par besoin, les lignes validées puis une ligne en brouillon
  const brouillonMatiere = (needId) => data.materials.find((m) => m.need_id === needId && etatDe(m) === 'draft')
  const figeesMatiere = (needId) => data.materials.filter((m) => m.need_id === needId && etatDe(m) !== 'draft')
  const setQuantite = (needId, v) => change((d) => {
    const i = d.materials.findIndex((m) => m.need_id === needId && etatDe(m) === 'draft')
    if (i >= 0) {
      if (v === '' || Number(v)) d.materials[i].quantity = v
      else d.materials.splice(i, 1)
    } else if (Number(v)) {
      d.materials.push({ uid: newId(), need_id: needId, quantity: v })
    }
  })
  const theorique = () => change((d) => {
    for (const n of phase.needs) {
      const deja = d.materials.filter((m) => m.need_id === n.id && etatDe(m) !== 'draft')
        .reduce((s, m) => s + (Number(m.quantity) || 0), 0)
      const q = Math.max(0, Math.round(((n.qty * qty) / phase.qty - deja) * 1000) / 1000)
      const i = d.materials.findIndex((m) => m.need_id === n.id && etatDe(m) === 'draft')
      if (i >= 0) d.materials[i].quantity = q
      else if (q) d.materials.push({ uid: newId(), need_id: n.id, quantity: q })
    }
  })

  return (
    <section className={`card work ${etat !== 'draft' ? 'work-locked' : ''}`}>
      <button type="button" className="work-head" onClick={() => setDeplie((o) => !o)} aria-expanded={deplie}>
        <Ring value={apres} />
        <div className="row-main">
          {phase?.path && <span className="muted small">{phase.path}</span>}
          <strong>{phase?.name ?? 'Phase introuvable'}</strong>
          <span className="work-summary">
            {phase?.qty ? `+${nombre(qty)} ${phase.unit ?? ''}` : label(snap.selections.work_status, data.status)}
            {' · '}{data.labor.length} ouvrier{data.labor.length > 1 ? 's' : ''} · {nombre(heures, 1)} h
          </span>
        </div>
        <span className={`chevron ${deplie ? 'open' : ''}`}><Icon name="down" size={18} /></span>
      </button>
      <div className="btn-row" style={{ alignItems: 'center' }}>
        {etatBadge}
        <span className="muted small">{Math.round(avant)}% → <strong>{Math.round(apres)}%</strong></span>
      </div>

      {conflit && (
        <Banner tone="danger" title="Conflit avec Odoo" actions={
          <>
            {conflit.reason !== 'deleted' && (
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => resoudre('works', work.uid, 'serveur')}>
                Garder la version d'Odoo
              </button>
            )}
            {conflit.reason === 'locked' && (
              <button type="button" className="btn btn-sm btn-primary" onClick={() => {
                ajouterLigneDepuis(projectId, date, data)
                resoudre('works', work.uid, 'serveur')
              }}>
                Mettre ma saisie dans une nouvelle ligne
              </button>
            )}
            {conflit.reason === 'modified' && (
              <button type="button" className="btn btn-sm btn-primary" onClick={() => resoudre('works', work.uid, 'mien')}>
                Envoyer ma version
              </button>
            )}
            {conflit.reason === 'deleted' && (
              <>
                <button type="button" className="btn btn-sm btn-primary" onClick={() => resoudre('works', work.uid, 'mien')}>
                  Recréer la ligne
                </button>
                <button type="button" className="btn btn-sm btn-ghost" onClick={() => abandonner('works', work.uid)}>
                  Abandonner
                </button>
              </>
            )}
          </>
        }>
          {conflit.message}
        </Banner>
      )}
      {work.local?.status === 'error' && <Banner tone="danger" title="Refusé par Odoo">{work.local.error}</Banner>}

      {deplie && phase && (
        <div className="work-body">
          {/* Réalisé */}
          <div className="work-block">
            <h3 className="group-title">Réalisé</h3>
            {phase.qty ? (
              <>
                <Stepper value={data.qty_done} step={1} min={null} unit={phase.unit} label="Quantité réalisée"
                  readOnly={fige} onChange={(v) => change((d) => { d.qty_done = v })} />
                <p className="muted small">
                  Validé jusqu'ici {nombre(phase.qty_done)} sur {nombre(phase.qty)} {phase.unit} · reste {nombre(Math.max(0, phase.qty - phase.qty_done))}
                </p>
                {qty < 0 && (
                  <input className="input" placeholder="Motif de la correction *" value={data.correction_reason ?? ''}
                    readOnly={fige} onChange={(e) => change((d) => { d.correction_reason = e.target.value })} />
                )}
              </>
            ) : (
              <Segmented columns={3} value={data.status} options={snap.selections.work_status} disabled={fige}
                onChange={(s) => s && change((d) => { d.status = s })} />
            )}
          </div>

          {/* Équipe */}
          <div className="work-block">
            <h3 className="group-title">Équipe</h3>
            {data.labor.map((l, i) => {
              const e = employe(l.employee_id)
              const le = etatDe(l)
              const lf = fige || le !== 'draft'
              return (
                <div key={l.uid ?? i} className={classeLigne(le)}>
                  <span className="avatar avatar-sm">{e?.name.slice(0, 1).toUpperCase() ?? '?'}</span>
                  <div className="row-main">
                    <strong>{e?.name ?? 'Ouvrier'}</strong>
                    {e?.trade && <span>{e.trade}</span>}
                  </div>
                  <Stepper value={l.hours} step={0.5} unit="h" label={`Heures de ${e?.name}`} readOnly={lf}
                    onChange={(v) => change((d) => { d.labor[i].hours = v })} />
                  <CheckBtn etat={le} disabled={fige || !(Number(l.hours) > 0)}
                    onClick={() => demanderValidation(setAsk, `les heures de ${e?.name ?? "l'ouvrier"}`,
                      () => change((d) => { d.labor[i].validate = true }), ' (coût de main-d\'œuvre)')} />
                  {!lf && (
                    <button type="button" className="check-btn" style={{ borderColor: 'var(--border)', color: 'var(--muted)' }}
                      aria-label="Retirer" onClick={() => change((d) => { d.labor.splice(i, 1) })}>
                      <Icon name="close" size={16} />
                    </button>
                  )}
                </div>
              )
            })}
            {!fige && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setChoixOuvriers(true)}>
                <Icon name="users" size={18} /> Ajouter des ouvriers
              </button>
            )}
          </div>

          {/* Matières */}
          {phase.needs.length > 0 && (
            <div className="work-block">
              <div className="block-head">
                <h3 className="group-title">Matières consommées</h3>
                {!fige && phase.qty > 0 && qty > 0 && (
                  <button type="button" className="link-btn accent" onClick={theorique}>Remplir le théorique</button>
                )}
              </div>
              {phase.needs.map((n) => {
                const brouillon = brouillonMatiere(n.id)
                return (
                  <div key={n.id} className="list" style={{ gap: 6 }}>
                    {figeesMatiere(n.id).map((m) => (
                      <div key={m.uid} className={classeLigne(etatDe(m))}>
                        <div className="row-main"><strong>{n.product}</strong><span>sortie du stock</span></div>
                        <Stepper value={m.quantity} unit={n.uom} readOnly />
                        <CheckBtn etat={etatDe(m)} />
                      </div>
                    ))}
                    {!fige && (
                      <div className="line">
                        <div className="row-main">
                          <strong>{n.product}</strong>
                          <span>Reste {nombre(n.remaining)} / {nombre(n.qty)} {n.uom}</span>
                        </div>
                        <Stepper value={brouillon?.quantity ?? ''} unit={n.uom} label={`Quantité de ${n.product}`}
                          onChange={(v) => setQuantite(n.id, v)} />
                        <CheckBtn etat="draft" disabled={!(Number(brouillon?.quantity) > 0)}
                          onClick={() => demanderValidation(setAsk, `${nombre(brouillon.quantity)} ${n.uom} de ${n.product}`,
                            () => change((d) => { d.materials.find((m) => m.uid === brouillon.uid).validate = true }),
                            ' : la matière sort du stock')} />
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Matériel et dépenses */}
          <div className="work-block">
            <MaterielLignes app={app} lignes={data.equipment} fige={fige} setAsk={setAsk}
              change={(fn) => change((d) => fn(d.equipment))} />
            <DepenseLignes app={app} lignes={data.expenses} fige={fige} setAsk={setAsk}
              change={(fn) => change((d) => fn(d.expenses))} />
          </div>

          {!fige && erreurs.length > 0 && <ul className="form-errors">{erreurs.map((e) => <li key={e}>{e}</li>)}</ul>}

          <div className="work-actions">
            {!fige && (
              <button type="button" className="btn btn-primary" disabled={erreurs.length > 0}
                onClick={() => setAsk({
                  title: 'Valider ce travail ?',
                  text: `Il sera figé avec toutes ses lignes : ${phase.qty ? `les ${nombre(qty)} ${phase.unit ?? ''} réalisés` : 'son état'} comptent dans l'avancement, ses matières sortent du stock. Seul le conducteur de travaux pourra l'annuler.`,
                  ok: 'Valider le travail',
                  onOk: () => saveWork(projectId, date, work.uid, data, { validate: true }),
                })}>
                <Icon name="check" size={18} /> Valider le travail
              </button>
            )}
            {etat !== 'draft' && !journalValide && (
              <button type="button" className="btn btn-soft" onClick={() => ajouterLigne(data.task_id)}>
                <Icon name="plus" size={18} /> Nouvelle ligne sur cette phase
              </button>
            )}
            {supprimable && (
              <button type="button" className="btn btn-danger" style={{ flex: 'none' }} aria-label="Supprimer la ligne"
                onClick={() => setAsk({
                  title: 'Supprimer cette ligne ?', text: `« ${phase.name} » sera retirée du journal.`,
                  ok: 'Supprimer', danger: true, onOk: () => supprimerWork(projectId, date, work.uid),
                })}>
                <Icon name="trash" size={18} />
              </button>
            )}
          </div>
        </div>
      )}

      {choixOuvriers && (
        <EmployeePicker employees={snap.employees}
          exclude={data.labor.filter((l) => etatDe(l) === 'draft').map((l) => l.employee_id)}
          onClose={() => setChoixOuvriers(false)}
          onPick={(ids) => {
            setChoixOuvriers(false)
            change((d) => { d.labor.push(...ids.map((id) => ({ uid: newId(), employee_id: id, hours: snap.hours_per_day }))) })
          }} />
      )}
    </section>
  )
}

/** Conflit sur un travail validé entre-temps : la saisie du téléphone part
 *  dans une nouvelle ligne, sans ce qui était déjà validé. */
function ajouterLigneDepuis(projectId, date, data) {
  const brouillon = (lines) => lines.filter((l) => etatDe(l) === 'draft')
    .map(({ state: _s, validate: _v, ...l }) => ({ ...l, uid: newId() }))
  saveWork(projectId, date, newId(), {
    ...data,
    labor: brouillon(data.labor), materials: brouillon(data.materials),
    equipment: brouillon(data.equipment), expenses: brouillon(data.expenses),
  })
}

function MaterielLignes({ app, lignes, fige, change, setAsk }) {
  const [choix, setChoix] = useState(false)
  const nom = (id) => app.snapshot.equipment.find((e) => e.id === id)?.name ?? 'Matériel'
  if (fige && !lignes.length) return null
  return (
    <>
      <h3 className="group-title">Matériel</h3>
      {lignes.map((l, i) => {
        const le = etatDe(l)
        const lf = fige || le !== 'draft'
        return (
          <div key={l.uid ?? i} className={classeLigne(le)}>
            <span className="tile tile-sm"><Icon name="crane" size={16} /></span>
            <div className="row-main"><strong>{nom(l.equipment_id)}</strong></div>
            <Stepper value={l.hours} step={0.5} unit="h" label={`Heures de ${nom(l.equipment_id)}`} readOnly={lf}
              onChange={(v) => change((ls) => { ls[i].hours = v })} />
            <CheckBtn etat={le} disabled={fige}
              onClick={() => demanderValidation(setAsk, `la ligne « ${nom(l.equipment_id)} »`,
                () => change((ls) => { ls[i].validate = true }))} />
            {!lf && (
              <button type="button" className="check-btn" style={{ borderColor: 'var(--border)', color: 'var(--muted)' }}
                aria-label="Retirer" onClick={() => change((ls) => { ls.splice(i, 1) })}>
                <Icon name="close" size={16} />
              </button>
            )}
          </div>
        )
      })}
      {!fige && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setChoix(true)}>
          <Icon name="plus" size={16} /> Matériel
        </button>
      )}
      {choix && (
        <EquipmentPicker equipment={app.snapshot.equipment}
          exclude={lignes.filter((l) => etatDe(l) === 'draft').map((l) => l.equipment_id)}
          onClose={() => setChoix(false)}
          onPick={(id) => {
            setChoix(false)
            change((ls) => { ls.push({ uid: newId(), equipment_id: id, hours: app.snapshot.hours_per_day }) })
          }} />
      )}
    </>
  )
}

function DepenseLignes({ app, lignes, fige, change, setAsk }) {
  if (fige && !lignes.length) return null
  return (
    <>
      <h3 className="group-title">Dépenses</h3>
      {lignes.map((l, i) => {
        const le = etatDe(l)
        const lf = fige || le !== 'draft'
        return (
          <div key={l.uid ?? i} className={classeLigne(le)}>
            <input className="input grow" placeholder="Libellé (transport, achat…)" value={l.name ?? ''} readOnly={lf}
              onChange={(e) => change((ls) => { ls[i].name = e.target.value })} />
            <input className="input amount-input" type="number" inputMode="decimal" min="0" step="any" readOnly={lf}
              placeholder={app.snapshot.currency} value={l.amount ?? ''}
              onChange={(e) => change((ls) => { ls[i].amount = e.target.value === '' ? '' : Number(e.target.value) })} />
            <CheckBtn etat={le} disabled={fige || !l.name?.trim()}
              onClick={() => demanderValidation(setAsk, `la dépense « ${l.name} »`,
                () => change((ls) => { ls[i].validate = true }))} />
            {!lf && (
              <button type="button" className="check-btn" style={{ borderColor: 'var(--border)', color: 'var(--muted)' }}
                aria-label="Retirer" onClick={() => change((ls) => { ls.splice(i, 1) })}>
                <Icon name="close" size={16} />
              </button>
            )}
          </div>
        )
      })}
      {!fige && (
        <button type="button" className="btn btn-ghost btn-sm"
          onClick={() => change((ls) => { ls.push({ uid: newId(), name: '', amount: '' }) })}>
          <Icon name="plus" size={16} /> Dépense
        </button>
      )}
    </>
  )
}
