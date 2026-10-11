import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/geist/index.css'
import '@fontsource-variable/geist-mono/index.css'
import '@fontsource-variable/noto-sans-devanagari/index.css'
import './index.css'
import './redesign.css'
import './evidence.css'
import V2App from './app/V2App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <V2App />
  </StrictMode>,
)
