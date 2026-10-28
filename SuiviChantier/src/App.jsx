import { useEffect, useState } from 'react'
import { enAttente, incidentsView, today, useApp } from './store.js'
import { Icon, Modal, TopBar } from './components/ui.jsx'
import Login from './components/Login.jsx'
import Dashboard from './components/Dashboard.jsx'
import ChantierDetail from './components/ChantierDetail.jsx'
import JournalEditor from './components/JournalEditor.jsx'
import Incidents from './components/Incidents.jsx'

// La navigation passe par l'historique du navigateur : le bouton retour
// d'Android (géré par Capacitor) ramène ainsi à l'écran précédent.
function useRoute() {
  const [route, setRoute] = useState(() => history.state ?? { name: 'home' })

  useEffect(() => {
    if (!history.state) history.replaceState({ name: 'home' }, '')
    const onPop = (e) => setRoute(e.state ?? { name: 'home' })
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = (next, { replace = false } = {}) => {
    if (replace) history.replaceState(next, '')
    else history.pushState(next, '')
    setRoute(next)
    if (!replace) window.scrollTo(0, 0)
  }

  return { route, navigate, back: () => history.back() }
}

export default function App() {
  const app = useApp()
  const { route, navigate, back } = useRoute()
  const [choixChantier, setChoixChantier] = useState(false)

  if (!app.loaded) return <div className="splash"><span className="brand-logo"><Icon name="crane" size={28} /></span></div>
  if (!app.session?.token) return <Login session={app.session} enAttente={enAttente(app)} />

  const projets = app.snapshot?.projects ?? []
  const projet = (id) => projets.find((p) => p.id === id)
  let screen
  if (app.snapshot && route.name === 'project' && projet(route.id)) {
    screen = <ChantierDetail key={route.id} app={app} project={projet(route.id)} route={route} navigate={navigate} back={back} />
  } else if (app.snapshot && route.name === 'journal' && projet(route.projectId)) {
    screen = <JournalEditor key={`${route.projectId}|${route.date}`} app={app} projectId={route.projectId} date={route.date} back={back} />
  } else if (app.snapshot && route.name === 'incidents') {
    screen = (
      <>
        <TopBar title="Incidents" subtitle="Tous vos chantiers" />
        <Incidents app={app} project={null} />
      </>
    )
  } else {
    screen = <Dashboard app={app} navigate={navigate} />
  }

  const journalDuJour = () => {
    if (projets.length === 1) navigate({ name: 'journal', projectId: projets[0].id, date: today() })
    else setChoixChantier(true)
  }
  const pleinEcran = route.name === 'journal'
  const incidentsOuverts = incidentsView(app).filter((i) => i.etat !== 'resolu').length

  return (
    <div className="app">
      {app.storageError && (
        <div className="alert">Mémoire du téléphone pleine : les dernières saisies ne sont pas enregistrées.</div>
      )}
      <main className={`screen ${pleinEcran ? 'screen-full' : ''}`}>{screen}</main>
      {!pleinEcran && (
        <nav className="tabbar" aria-label="Navigation">
          <button type="button" aria-label="Chantiers" title="Chantiers"
            className={route.name === 'home' || route.name === 'project' ? 'active' : ''}
            onClick={() => navigate({ name: 'home' })}>
            <Icon name="home" size={22} />
          </button>
          <button type="button" aria-label="Journal du jour" title="Journal du jour" onClick={journalDuJour}
            disabled={!projets.length}>
            <Icon name="book" size={22} />
          </button>
          <button type="button" aria-label="Incidents" title="Incidents"
            className={route.name === 'incidents' ? 'active' : ''}
            onClick={() => navigate({ name: 'incidents' })}>
            <Icon name="flag" size={22} />
            {incidentsOuverts > 0 && <span className="count">{incidentsOuverts}</span>}
          </button>
        </nav>
      )}

      {choixChantier && (
        <Modal title="Journal du jour : quel chantier ?" onClose={() => setChoixChantier(false)}>
          <div className="list">
            {projets.map((p) => (
              <button type="button" key={p.id} className="list-row" onClick={() => {
                setChoixChantier(false)
                navigate({ name: 'journal', projectId: p.id, date: today() })
              }}>
                <span className="tile tile-soft"><Icon name="building" size={18} /></span>
                <div className="row-main">
                  <strong>{p.name}</strong>
                  {p.address && <span>{p.address}</span>}
                </div>
                <Icon name="chevron" />
              </button>
            ))}
          </div>
        </Modal>
      )}
    </div>
  )
}
