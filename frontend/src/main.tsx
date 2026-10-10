import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/bricolage-grotesque/index.css'
import '@fontsource-variable/figtree/index.css'
import '@fontsource-variable/jetbrains-mono/index.css'
import '@fontsource-variable/noto-sans-devanagari/index.css'
import './index.css'
import V2App from './app/V2App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <V2App />
  </StrictMode>,
)
