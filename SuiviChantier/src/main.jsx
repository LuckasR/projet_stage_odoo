import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/urbanist'
import './index.css'
import App from './App.jsx'
import { demarrer } from './store.js'

demarrer()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
