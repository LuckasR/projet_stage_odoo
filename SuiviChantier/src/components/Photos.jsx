import { useState } from 'react'
import { ajouterPhoto, photosDe, retirerPhoto, useApp } from '../store.js'
import { Icon, Lightbox, Photo } from './ui.jsx'

/** Photos d'un journal ou d'un incident. Celles prises sur le téléphone
 *  partent à la prochaine synchronisation ; d'ici là on peut les retirer. */
export default function Photos({ target, refKey, serverPhotos, editable = true }) {
  const app = useApp()
  const [zoom, setZoom] = useState(null)
  const [chargement, setChargement] = useState(false)
  const photos = photosDe(app, target, refKey, serverPhotos)

  const ajouter = async (e) => {
    const files = [...e.target.files]
    e.target.value = ''
    setChargement(true)
    try {
      for (const f of files) await ajouterPhoto(target, refKey, f)
    } finally {
      setChargement(false)
    }
  }

  return (
    <div className="photos">
      {photos.map((p) => (
        <div key={p.key} className={`photo ${p.localId ? 'photo-pending' : ''}`}>
          <Photo photo={p} onClick={setZoom} />
          {p.localId && editable && (
            <button type="button" className="photo-remove" aria-label="Retirer la photo"
              onClick={() => retirerPhoto(p.localId)}>
              <Icon name="close" size={14} />
            </button>
          )}
        </div>
      ))}
      {editable && (
        <label className="photo-add">
          <Icon name="camera" />
          <span>{chargement ? '…' : 'Photo'}</span>
          <input type="file" accept="image/*" capture="environment" multiple hidden onChange={ajouter} />
        </label>
      )}
      {!editable && photos.length === 0 && <span className="muted small">Aucune photo.</span>}
      <Lightbox url={zoom} onClose={() => setZoom(null)} />
    </div>
  )
}
