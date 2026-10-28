import { useEffect, useState } from 'react'
import { photoBlob } from '../store.js'

const ICONS = {
  home: 'M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  back: 'M15 18l-6-6 6-6',
  chevron: 'M9 6l6 6-6 6',
  down: 'M6 9l6 6 6-6',
  arrow: 'M7 17L17 7M8 7h9v9',
  close: 'M18 6L6 18M6 6l12 12',
  trash: 'M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14',
  pin: 'M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12zM12 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
  camera: 'M4 7h3l2-3h6l2 3h3a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
  check: 'M5 12l5 5L20 7',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-5-5',
  sync: 'M21 12a9 9 0 0 1-15.5 6.2M3 12a9 9 0 0 1 15.5-6.2M18 3v4h-4M6 21v-4h4',
  offline: 'M2 2l20 20M17.5 17.5H7a5 5 0 0 1-1.6-9.7M10 5.4A6 6 0 0 1 19.8 9a4 4 0 0 1 2 6.6',
  alert: 'M12 3l10 18H2zM12 10v4M12 17h.01',
  logout: 'M15 4h4v16h-4M10 17l5-5-5-5M15 12H3',
  calendar: 'M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM4 10h16M8 3v4M16 3v4M8 14h2M14 14h2',
  copy: 'M8 8h12v12H8zM4 16V4h12',
  send: 'M22 2L11 13M22 2l-7 20-4-9-9-4z',
  book: 'M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11',
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
  users: 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M16 3.5a4 4 0 0 1 0 7M22 21a7 7 0 0 0-4-6.3',
  building: 'M5 21V5a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v16M15 9h3a1 1 0 0 1 1 1v11M3 21h18M8.5 8h3M8.5 12h3M8.5 16h3',
  dots: 'M12 5h.01M12 12h.01M12 19h.01',
  lock: 'M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4',
  layers: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5',
  crane: 'M4 21V6l5-3v18M9 6h11M18 6v5M16 11h4M2 21h10',
}

export function Icon({ name, size = 20, stroke = 2 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  )
}

/** Bouton carré à icône, comme sur les maquettes. */
export function Tile({ icon, label, onClick, tone = '', size = 20, count, ...rest }) {
  return (
    <button type="button" className={`tile ${tone} ${count != null ? 'tile-badge' : ''}`}
      aria-label={label} title={label} onClick={onClick} data-count={count} {...rest}>
      <Icon name={icon} size={size} />
    </button>
  )
}

/** En-tête d'écran : retour, titre centré, action à droite. */
export function TopBar({ title, subtitle, onBack, right }) {
  return (
    <header className="topbar">
      {onBack ? <Tile icon="back" label="Retour" onClick={onBack} /> : <span />}
      <div className="topbar-title">
        <h1 className="capitalize">{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {right ?? <span />}
    </header>
  )
}

/** Pourcentage dans une tuile cerclée d'un arc orange. */
export function Ring({ value, size = 50 }) {
  const v = Math.max(0, Math.min(100, Math.round(value)))
  return (
    <span className={`ring ${v >= 100 ? 'done' : ''}`} style={{ width: size, height: size }}
      role="img" aria-label={`${v} %`}>
      <svg viewBox="0 0 50 50">
        <defs>
          <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#f8bc4f" />
            <stop offset="100%" stopColor="#e65f10" />
          </linearGradient>
        </defs>
        <rect className="ring-track" x="2" y="2" width="46" height="46" rx="15" />
        <rect className="ring-value" x="2" y="2" width="46" height="46" rx="15" pathLength="100"
          strokeDasharray={`${v} 100`} />
      </svg>
      <span>{v}%</span>
    </span>
  )
}

/** Réglette : graduations grises, orange jusqu'à la valeur. */
export function Ticks({ value, count = 34 }) {
  const on = Math.round((Math.max(0, Math.min(100, value)) / 100) * count)
  return (
    <div className="ticks" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className={i < on ? (i === on - 1 ? 'on cap' : 'on') : ''} />
      ))}
    </div>
  )
}

/** Barre hachurée avec un repère (aujourd'hui). */
export function HatchBar({ value, mark }) {
  return (
    <div className="hatchbar" role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin="0" aria-valuemax="100">
      <div className="hatchbar-track" />
      <div className="hatchbar-fill" style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
      {mark != null && <div className="hatchbar-mark" style={{ left: `${Math.max(1, Math.min(99, mark))}%` }} />}
    </div>
  )
}

export function Badge({ tone = 'info', children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

export function Banner({ tone = 'warn', icon = 'alert', title, children, actions }) {
  return (
    <div className={`banner banner-${tone}`} role="status">
      <Icon name={icon} />
      <div className="banner-body">
        {title && <strong>{title}</strong>}
        {children && <div>{children}</div>}
        {actions && <div className="banner-actions">{actions}</div>}
      </div>
    </div>
  )
}

export function Modal({ title, onClose, children, footer }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}
        onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <h2>{title}</h2>
          <Tile icon="close" label="Fermer" onClick={onClose} tone="tile-sm" />
        </header>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}

/** Confirmation en feuille, à la place de window.confirm. */
export function Confirm({ ask, onClose }) {
  if (!ask) return null
  return (
    <Modal title={ask.title} onClose={onClose}>
      {ask.text && <p className="muted">{ask.text}</p>}
      <div className="btn-row">
        <button type="button" className="btn btn-ghost grow" onClick={onClose}>Annuler</button>
        <button type="button" className={`btn grow ${ask.danger ? 'btn-danger' : 'btn-primary'}`}
          onClick={() => { onClose(); ask.onOk() }}>
          {ask.ok ?? 'Confirmer'}
        </button>
      </div>
    </Modal>
  )
}

export function useForm(initial) {
  const [values, setValues] = useState(initial)
  const bind = (field) => ({
    value: values[field] ?? '',
    onChange: (e) => setValues((v) => ({ ...v, [field]: e.target.value })),
  })
  return { values, setValues, bind }
}

export function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  )
}

export function Empty({ children }) {
  return <p className="empty">{children}</p>
}

const arrondi = (v) => Math.round(v * 1000) / 1000

/** Nombre au pouce : gros boutons − / + et saisie directe au clavier.
 *  Figé (`readOnly`), il n'affiche plus que la valeur. */
export function Stepper({ value, onChange, step = 1, min = 0, unit, label, readOnly }) {
  if (readOnly) return <span className="value-pill">{value === '' ? 0 : value}{unit ? ` ${unit}` : ''}</span>
  const n = Number(value) || 0
  const set = (v) => onChange(min == null ? arrondi(v) : Math.max(min, arrondi(v)))
  return (
    <div className="stepper">
      <button type="button" onClick={() => set(n - step)} aria-label={`Moins ${step}`}
        disabled={min != null && n <= min}>
        <Icon name="minus" size={18} />
      </button>
      <input type="number" inputMode="decimal" step="any" aria-label={label}
        value={value === '' ? '' : value}
        onFocus={(e) => e.target.select()}
        onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))} />
      {unit && <span className="stepper-unit">{unit}</span>}
      <button type="button" onClick={() => set(n + step)} aria-label={`Plus ${step}`}>
        <Icon name="plus" size={18} />
      </button>
    </div>
  )
}

/** Choix exclusif en gros boutons, plutôt qu'une liste déroulante. */
export function Segmented({ options, value, onChange, columns, disabled }) {
  return (
    <div className="segmented" style={columns ? { gridTemplateColumns: `repeat(${columns}, 1fr)` } : undefined}>
      {options.map(([key, text, extra]) => (
        <button type="button" key={key} className={value === key ? 'active' : ''} aria-pressed={value === key}
          disabled={disabled} onClick={() => onChange(value === key ? null : key)}>
          {extra && <span className="segmented-extra">{extra}</span>}
          <span>{text}</span>
        </button>
      ))}
    </div>
  )
}

export function Photo({ photo, onClick }) {
  const [url, setUrl] = useState(null)
  const [erreur, setErreur] = useState(false)

  useEffect(() => {
    let objectUrl
    let actif = true
    photoBlob(photo).then(
      (blob) => {
        if (!actif || !blob) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      },
      () => actif && setErreur(true),
    )
    return () => {
      actif = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [photo.key]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!url) return <span className="photo-placeholder">{erreur ? 'Hors-ligne' : '…'}</span>
  return onClick
    ? <button type="button" className="photo-btn" onClick={() => onClick(url)} aria-label="Agrandir la photo"><img src={url} alt="" /></button>
    : <img src={url} alt="" />
}

export function Lightbox({ url, onClose }) {
  if (!url) return null
  return (
    <div className="lightbox" onClick={onClose} role="dialog" aria-label="Photo">
      <img src={url} alt="" />
    </div>
  )
}
