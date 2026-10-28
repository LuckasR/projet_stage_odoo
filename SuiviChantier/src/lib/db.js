// IndexedDB : l'état de l'application (une seule entrée) et les photos.
// localStorage est trop petit (~5 Mo) et ne garde que du texte ; ici les
// photos restent des fichiers (Blob), sans conversion en base64.

const DB_NAME = 'suivichantier'
const VERSION = 1

let dbPromise

function open() {
  dbPromise ??= new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, VERSION)
    req.onupgradeneeded = () => {
      req.result.createObjectStore('kv')
      req.result.createObjectStore('photos')
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
  return dbPromise
}

async function run(store, mode, fn) {
  const db = await open()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode)
    const req = fn(tx.objectStore(store))
    tx.oncomplete = () => resolve(req.result)
    tx.onerror = tx.onabort = () => reject(tx.error)
  })
}

function table(name) {
  return {
    get: (key) => run(name, 'readonly', (s) => s.get(key)),
    put: (key, value) => run(name, 'readwrite', (s) => s.put(value, key)),
    delete: (key) => run(name, 'readwrite', (s) => s.delete(key)),
    clear: () => run(name, 'readwrite', (s) => s.clear()),
  }
}

export const kv = table('kv')
export const photoStore = table('photos')
