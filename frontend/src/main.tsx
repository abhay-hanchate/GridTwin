import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { V2_DASHBOARD } from './api/v2'
import V2App from './app/V2App'

// The Round 1 dashboard stays the default until the v2 API serves real results (merge point M3).
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {V2_DASHBOARD ? <V2App /> : <App />}
  </StrictMode>,
)
