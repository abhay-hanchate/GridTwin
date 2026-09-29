import { lazy, Suspense, useState } from 'react'
import { useApi } from './api'
import { SCENARIO_TEXT } from './plain'
import type { Insights, Scenario, ScenarioId } from './types'

type Tab = 'story' | 'grid' | 'fixes' | 'forecast' | 'capacity'

const TABS: [Tab, string][] = [
  ['story', '1 · The story'], ['grid', '2 · Live map'], ['fixes', '3 · Fixes'], ['forecast', '4 · AI forecast'],
  ['capacity', '5 · Hosting capacity'],
]

// Each screen is its own chunk, downloaded the first time its tab is opened (or hovered).
const LOADERS = {
  story: () => import('./components/StoryView'),
  grid: () => import('./components/GridView'),
  fixes: () => import('./components/FixesView'),
  forecast: () => import('./components/ForecastView'),
  capacity: () => import('./components/CapacityView'),
} satisfies Record<Tab, () => Promise<unknown>>

const StoryView = lazy(LOADERS.story)
const GridView = lazy(LOADERS.grid)
const FixesView = lazy(LOADERS.fixes)
const ForecastView = lazy(LOADERS.forecast)
const CapacityView = lazy(LOADERS.capacity)

const prefetch = (id: Tab) => { void LOADERS[id]() }

export default function App() {
  const [tab, setTab] = useState<Tab>('story')
  const [scenario, setScenario] = useState<ScenarioId>('S4')
  const scenarios = useApi<Scenario[]>('/api/scenarios')
  const insights = useApi<Insights>('/api/insights')

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <img className="brand-mark" src="/favicon.svg" alt="" />
          <div>
            <h1>GridTwin</h1>
            <p>Can a street's wiring handle solar on every roof? A computer copy of the street finds out.</p>
          </div>
        </div>
        <nav className="tabs" aria-label="Views">
          {TABS.map(([id, label]) => (
            <button key={id} className={`tab ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}
              onMouseEnter={() => prefetch(id)} onFocus={() => prefetch(id)}>{label}</button>
          ))}
        </nav>
      </header>

      {tab !== 'story' && insights.data && (
        <section className="insight" aria-label="Measured voltage quality">
          <div><strong>{insights.data.median_v} V</strong><div className="label">typical voltage at real homes (should be 230 V)</div></div>
          <div><strong>{Math.round(insights.data.share_above_10pct * 100)}%</strong><div className="label">of the time above the 253 V safe limit</div></div>
          <div className="source">Measured by smart meters in {insights.data.meters} Mathura homes, 2019</div>
        </section>
      )}

      {(tab === 'grid' || tab === 'fixes') && scenarios.data && (
        <div className="toolbar">
          <span className="label">Which homes have solar?</span>
          <div className="segmented" role="radiogroup" aria-label="Scenario">
            {scenarios.data.map((s) => (
              <button key={s.id} role="radio" aria-checked={scenario === s.id} title={SCENARIO_TEXT[s.id].long}
                className={`seg ${scenario === s.id ? 'active' : ''}`} onClick={() => setScenario(s.id)}>
                {SCENARIO_TEXT[s.id].short}
              </button>
            ))}
          </div>
        </div>
      )}

      <main style={{ marginTop: tab === 'story' ? 20 : 0 }}>
        <Suspense fallback={<div className="loading">Loading this screen…</div>}>
          {tab === 'story' && <StoryView go={setTab} />}
          {tab === 'grid' && <GridView scenario={scenario} />}
          {tab === 'fixes' && <FixesView scenario={scenario} />}
          {tab === 'forecast' && <ForecastView />}
          {tab === 'capacity' && <CapacityView />}
        </Suspense>
      </main>

      <footer className="footer">
        HackMatrix 5.0 · ENR-02 · Street layout: SimBench benchmark with Indian overhead wires · Electricity use and voltage:
        CEEW smart meters (CC0) · Weather: Open-Meteo
      </footer>
    </div>
  )
}
