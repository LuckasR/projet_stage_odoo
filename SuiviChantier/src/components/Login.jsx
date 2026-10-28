import { useState } from 'react'
import { normaliserUrl } from '../lib/api.js'
import { connecter } from '../store.js'
import { Banner, Field, Icon, useForm } from './ui.jsx'

export default function Login({ session, enAttente }) {
  const { values, bind } = useForm({
    url: session?.url ?? '',
    login: session?.login ?? '',
    password: '',
  })
  const [erreur, setErreur] = useState(null)
  const [envoi, setEnvoi] = useState(false)
  const expiree = Boolean(session?.login)

  const submit = async (e) => {
    e.preventDefault()
    setErreur(null)
    setEnvoi(true)
    try {
      await connecter(normaliserUrl(values.url), values.login.trim(), values.password)
    } catch (err) {
      setErreur(err.status === 0
        ? "Serveur injoignable. Vérifiez l'adresse et la connexion du téléphone."
        : err.message)
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <main className="screen login">
      <div className="login-brand">
        <span className="brand-logo"><Icon name="crane" size={36} /></span>
        <h1>SuiviChantier</h1>
        <p className="muted">Journal de chantier, avancement et incidents, connectés à Odoo.</p>
      </div>

      {expiree && enAttente > 0 && (
        <Banner tone="info" icon="sync" title="Votre session a expiré">
          Vos {enAttente} saisie{enAttente > 1 ? 's' : ''} non envoyée{enAttente > 1 ? 's' : ''} sont
          conservée{enAttente > 1 ? 's' : ''} sur le téléphone et partiront après la connexion.
        </Banner>
      )}

      <form className="card form" onSubmit={submit}>
        <Field label="Adresse du serveur Odoo">
          <input required inputMode="url" autoCapitalize="none" autoCorrect="off"
            placeholder="192.168.1.10:8069" {...bind('url')} />
        </Field>
        <Field label="Identifiant">
          <input required autoCapitalize="none" autoCorrect="off" autoComplete="username" {...bind('login')} />
        </Field>
        <Field label="Mot de passe">
          <input required type="password" autoComplete="current-password" {...bind('password')} />
        </Field>
        {erreur && <p className="form-error">{erreur}</p>}
        <button type="submit" className="btn btn-primary" disabled={envoi}>
          {envoi ? 'Connexion…' : 'Se connecter'}
        </button>
      </form>
    </main>
  )
}
