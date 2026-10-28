import { useState } from 'react'
import { nombre } from '../store.js'
import { ListePhases, Recherche, filtrerPhases } from './ChantierDetail.jsx'
import { Empty, Icon, Modal, Ring } from './ui.jsx'

/** Choix d'une phase : d'abord celles en cours, les finies en dernier.
 *  `dejaDuJour` compte les lignes que chaque phase a déjà aujourd'hui
 *  (une phase peut en avoir plusieurs). */
export function PhasePicker({ phases, dejaDuJour = {}, suggestions = [], onPick, onClose }) {
  const [recherche, setRecherche] = useState('')
  const [finies, setFinies] = useState(false)
  const visibles = filtrerPhases(phases, recherche, (p) => finies || p.progress < 100)
    .sort((a, b) => rang(a) - rang(b))
  const sugg = [...new Set(suggestions)].map((id) => phases.find((p) => p.id === id)).filter(Boolean)

  return (
    <Modal title="Choisir une phase" onClose={onClose}>
      <div className="picker">
        <Recherche value={recherche} onChange={setRecherche} placeholder="Rechercher une phase, un ouvrage…" />
        {!recherche && sugg.length > 0 && (
          <>
            <h3 className="group-title">Phases d'hier</h3>
            <div className="chips">
              {sugg.map((p) => (
                <button type="button" key={p.id} className="chip" onClick={() => onPick(p)}>{p.name}</button>
              ))}
            </div>
          </>
        )}
        <label className="check-row">
          <input type="checkbox" checked={finies} onChange={(e) => setFinies(e.target.checked)} />
          <span>Afficher les phases finies</span>
        </label>
        <ListePhases phases={visibles} renderRow={(p) => (
          <button type="button" key={p.id} className="list-row" onClick={() => onPick(p)}>
            <Ring value={p.progress} size={46} />
            <div className="row-main">
              <strong>{p.name}</strong>
              <span>
                {p.qty > 0 ? `${nombre(p.qty_done)} / ${nombre(p.qty)} ${p.unit ?? ''}` : 'Sans métré'}
                {p.crew && ` · ${p.crew}`}
                {dejaDuJour[p.id] ? ` · déjà ${dejaDuJour[p.id]} ligne${dejaDuJour[p.id] > 1 ? 's' : ''} aujourd'hui` : ''}
              </span>
            </div>
            <span className="tile tile-soft tile-sm"><Icon name="plus" size={18} /></span>
          </button>
        )} />
      </div>
    </Modal>
  )
}

// En cours d'abord, puis à faire, puis finies
const rang = (p) => (p.progress > 0 && p.progress < 100 ? 0 : p.progress === 0 ? 1 : 2)

/** Choix de plusieurs ouvriers d'un coup, avec leurs heures par défaut. */
export function EmployeePicker({ employees, exclude = [], onPick, onClose }) {
  const [recherche, setRecherche] = useState('')
  const [choix, setChoix] = useState([])
  const q = recherche.trim().toLowerCase()
  const dispo = employees
    .filter((e) => !exclude.includes(e.id))
    .filter((e) => !q || `${e.name} ${e.trade ?? ''}`.toLowerCase().includes(q))
  const basculer = (id) => setChoix((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))

  return (
    <Modal title="Ajouter des ouvriers" onClose={onClose}
      footer={
        <button type="button" className="btn btn-primary btn-block" disabled={!choix.length}
          onClick={() => onPick(choix)}>
          Ajouter {choix.length > 0 && `(${choix.length})`}
        </button>
      }>
      <div className="picker">
        <Recherche value={recherche} onChange={setRecherche} placeholder="Rechercher un ouvrier, un métier…" />
        {dispo.length === 0 && <Empty>Aucun ouvrier à ajouter.</Empty>}
        <div className="list">
          {dispo.map((e) => (
            <label key={e.id} className="list-row check-row">
              <span className="avatar avatar-sm">{e.name.slice(0, 1).toUpperCase()}</span>
              <div className="row-main">
                <strong>{e.name}</strong>
                {e.trade && <span>{e.trade}</span>}
              </div>
              <input type="checkbox" checked={choix.includes(e.id)} onChange={() => basculer(e.id)} />
            </label>
          ))}
        </div>
      </div>
    </Modal>
  )
}

export function EquipmentPicker({ equipment, exclude = [], onPick, onClose }) {
  const dispo = equipment.filter((e) => !exclude.includes(e.id))
  return (
    <Modal title="Ajouter du matériel" onClose={onClose}>
      {dispo.length === 0 && <Empty>Aucun matériel à ajouter.</Empty>}
      <div className="list">
        {dispo.map((e) => (
          <button type="button" key={e.id} className="list-row" onClick={() => onPick(e.id)}>
            <span className="tile tile-soft tile-sm"><Icon name="crane" size={18} /></span>
            <div className="row-main"><strong>{e.name}</strong></div>
            <Icon name="plus" />
          </button>
        ))}
      </div>
    </Modal>
  )
}
