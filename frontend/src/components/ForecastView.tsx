import {
  Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useApi, volts } from '../api'
import type { EarlyWarning, ForecastResult, ModelMetrics } from '../types'

function BandChart({ f, unit }: { f: ForecastResult; unit: string }) {
  const data = f.points.map((p) => ({ ...p, band: [p.p10, p.p90] }))
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
        <CartesianGrid stroke="#e8ebe6" vertical={false} />
        <XAxis dataKey="t" interval={11} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v) => (Array.isArray(v) ? `${v[0].toFixed(3)}–${v[1].toFixed(3)} ${unit}`
          : typeof v === 'number' ? `${v.toFixed(3)} ${unit}` : v)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area isAnimationActive={false} dataKey="band" name="Forecast range (P10–P90)" stroke="none" fill="#0f766e" fillOpacity={0.18} />
        <Line isAnimationActive={false} dataKey="p50" name="Forecast (P50)" stroke="#0f766e" strokeWidth={2} dot={false} />
        <Line isAnimationActive={false} dataKey="actual" name="What happened" stroke="#16201d" strokeDasharray="4 3" strokeWidth={1.6} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function Scores({ m }: { m: ModelMetrics }) {
  return (
    <div className="metrics-row">
      <div className="mini"><div className="v">{Math.round(m.skill_vs_persistence * 100)}%</div><div className="l">better than "same as yesterday"</div></div>
      <div className="mini"><div className="v">{Math.round(m.p10_p90_coverage * 100)}%</div><div className="l">of real values inside the range (target 80%)</div></div>
      <div className="mini"><div className="v">{m.mae_p50.toFixed(3)}</div><div className="l">mean error · test {m.test}</div></div>
    </div>
  )
}

export default function ForecastView() {
  const solar = useApi<ForecastResult>('/api/forecast?target=solar&date=2025-05-15')
  const demand = useApi<ForecastResult>('/api/forecast?target=demand&date=2019-11-20')
  const metrics = useApi<{ solar: ModelMetrics; demand: ModelMetrics }>('/api/metrics')
  const warn = useApi<EarlyWarning>('/api/early-warning')

  return (
    <div className="stack">
      <div className="card">
        <h2>Early warning · {warn.data?.date ?? '…'} with every home on solar</h2>
        <p className="sub">
          Tomorrow's solar forecast is run through the grid twin to predict unsafe voltage a day ahead, then compared with what happened.
          {warn.data && ` Demand uses the same calendar day of 2019 (${warn.data.demand_proxy_date}) as a labelled proxy.`}
        </p>
        {warn.data && (
          <div className="warn-grid">
            {(['p50', 'p90', 'actual'] as const).map((k) => {
              const c = warn.data!.cases[k]
              return (
                <div key={k} className={`warn-case ${k === 'actual' ? 'actual' : ''}`}>
                  <div className="muted">{k === 'p50' ? 'Predicted (likely solar)' : k === 'p90' ? 'Predicted (high solar)' : 'What actually happened'}</div>
                  <div className="v">{c.violation_steps} unsafe steps</div>
                  <div className="muted">peak {volts(c.max_vm_pu)} V · first at {c.first_unsafe ?? '—'}</div>
                </div>
              )
            })}
          </div>
        )}
        {warn.loading && <div className="loading">Running the forecast through the grid…</div>}
      </div>

      <div className="split">
        <div className="card">
          <h2>Solar forecast · 15 May 2025</h2>
          <p className="sub">LightGBM on the weather forecast issued the day before; truth is solar computed from ERA5 reanalysis.</p>
          {solar.data && <BandChart f={solar.data} unit="kW/kWp" />}
          {metrics.data && <Scores m={metrics.data.solar} />}
        </div>
        <div className="card">
          <h2>Household demand forecast · 20 Nov 2019</h2>
          <p className="sub">Average real CEEW household in Mathura; predicts the ratio to the same time yesterday.</p>
          {demand.data && <BandChart f={demand.data} unit="kW" />}
          {metrics.data && <Scores m={metrics.data.demand} />}
        </div>
      </div>
    </div>
  )
}
