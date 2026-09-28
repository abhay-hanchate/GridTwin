import { useState } from 'react'
import { useApi } from './api'
import FixesView from './components/FixesView'
import ForecastView from './components/ForecastView'
import GridView from './components/GridView'
import type { Insights, Scenario, ScenarioId } from './types'

type Tab = 'grid' | 'fixes' | 'forecast'

const TABS: [Tab, string][] = [['grid', 'Grid twin'], ['fixes', 'Fixes'], ['forecast', 'Forecast & early warning']]

export default function App() {
  const [tab, setTab] = useState<Tab>('grid')
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
            <p>Digital twin of a rural feeder under rooftop solar · real Mathura homes and weather</p>
          </div>
        </div>
        <nav className="tabs" aria-label="Views">
          {TABS.map(([id, label]) => (
            <button key={id} className={`tab ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
          ))}
        </nav>
      </header>

      {insights.data && (
        <section className="insight" aria-label="Measured voltage quality">
          <div><strong>{insights.data.median_v} V</strong><div className="label">median voltage at real homes (nominal 230 V)</div></div>
          <div><strong>{Math.round(insights.data.share_above_10pct * 100)}%</strong><div className="label">of readings above the +10% limit (253 V)</div></div>
          <div><strong>{Math.round(insights.data.share_below_10pct * 100)}%</strong><div className="label">below −10% (207 V)</div></div>
          <div className="source">CEEW smart meters · {insights.data.meters} Mathura homes · 2019</div>
        </section>
      )}

      {tab !== 'forecast' && scenarios.data && (
        <div className="toolbar">
          <span className="label">Scenario</span>
          <div className="segmented" role="radiogroup" aria-label="Scenario">
            {scenarios.data.map((s) => (
              <button key={s.id} role="radio" aria-checked={scenario === s.id}
                className={`seg ${scenario === s.id ? 'active' : ''}`} onClick={() => setScenario(s.id)}>
                <b>{s.id}</b>{s.name}
              </button>
            ))}
          </div>
        </div>
      )}

      <main>
        {tab === 'grid' && <GridView scenario={scenario} />}
        {tab === 'fixes' && <FixesView scenario={scenario} />}
        {tab === 'forecast' && <ForecastView />}
      </main>

      <footer className="footer">
        HackMatrix 5.0 · ENR-02 · Grid: SimBench benchmark with Indian overhead lines · Demand and voltage: CEEW (CC0) · Weather: Open-Meteo
      </footer>
    </div>
  )
}
