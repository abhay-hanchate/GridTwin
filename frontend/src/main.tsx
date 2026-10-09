import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import V2App from './app/V2App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <V2App />
  </StrictMode>,
)
