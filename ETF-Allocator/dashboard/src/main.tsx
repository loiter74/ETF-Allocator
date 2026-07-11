import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { applyMode, applyTheme, getSavedTheme } from './design-system/theme'

applyTheme(getSavedTheme())
applyMode('light')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
