import {
  Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useApi, volts } from '../api'
import { duration, niceDate } from '../plain'
import type { EarlyWarning, ForecastResult, GridTopology, LiveForecast, LiveWarning, ModelMetrics, SimResult } from '../types'
import TwinSim from './TwinSim'

function BandChart({ f, scale, unit }: { f: ForecastResult; scale: number; unit: string }) {
  const r = (v: number) => Math.round(v * scale * 10) / 10
  const data = f.points.map((p) => ({ t: p.t, p50: r(p.p50), actual: r(p.actual), band: [r(p.p10), r(p.p90)] }))
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: -4, bottom: 0 }}>
        <CartesianGrid stroke="#e8ebe6" vertical={false} />
        <XAxis dataKey="t" interval={11} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} unit={` ${unit}`} width={64} />
        <Tooltip formatter={(v) => (Array.isArray(v) ? `${v[0]}–${v[1]} ${unit}` : `${v} ${unit}`)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area isAnimationActive={false} dataKey="band" name="Range the AI is 80% sure about" stroke="none" fill="#0f766e" fillOpacity={0.18} />
        <Line isAnimationActive={false} dataKey="p50" name="AI prediction (made the day before)" stroke="#0f766e" strokeWidth={2} dot={false} />
        <Line isAnimationActive={false} dataKey="actual" name="ERA5/PVWatts reference" stroke="#16201d" strokeDasharray="4 3" strokeWidth={1.6} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function Scores({ m }: { m: ModelMetrics }) {
  return (
    <div className="metrics-row">
      <div className="mini"><div className="v">{Math.round(m.skill_vs_persistence * 100)}%</div><div className="l">more accurate than guessing "same as yesterday"</div></div>
      <div className="mini"><div className="v">{Math.round(m.p10_p90_coverage * 100)}%</div><div className="l">of real values fell inside the shaded range (aim: 80%)</div></div>
      <div className="mini"><div className="v">{m.test}</div><div className="l">tested on data the AI never saw (trained on {m.train})</div></div>
    </div>
  )
}

export default function ForecastView() {
  const live = useApi<LiveForecast>('/api/live-forecast')
  const liveWarn = useApi<LiveWarning>('/api/live-early-warning')
  const solar = useApi<ForecastResult>('/api/forecast?target=solar&date=2025-05-15')
  const demand = useApi<ForecastResult>('/api/forecast?target=demand&date=2019-11-20')
  const metrics = useApi<{ solar: ModelMetrics; demand: ModelMetrics }>('/api/metrics')
  const warn = useApi<EarlyWarning>('/api/early-warning')
  const sim = useApi<SimResult>('/api/forecast-sim')
  const grid = useApi<GridTopology>('/api/grid?scenario=S4')

  return (
    <div className="stack">
      <div className="how-strip">
        <div><b>1</b> Yesterday, the weather service forecasts tomorrow's sun, clouds and heat</div>
        <div><b>2</b> Our AI turns that forecast into solar power for every hour of tomorrow</div>
        <div><b>3</b> The computer copy of the street replays tomorrow with that solar</div>
        <div><b>4</b> We warn: when, where and for how long voltage will be unsafe</div>
      </div>
      <div className="card">
        <h2>Live tomorrow forecast{live.data ? ` · ${niceDate(live.data.date)}` : ''}</h2>
        <p className="sub">
          This card fetches the latest keyless Open-Meteo weather forecast and runs the frozen LightGBM quantile ensemble at request time.
          It is operational inference; the historical cards below remain the audited comparison against ERA5/PVWatts.
        </p>
        {live.loading && <div className="loading">Fetching tomorrow's weather and running the solar model…</div>}
        {live.error && <div className="muted">Live forecast unavailable: {live.error}</div>}
        {live.data && (
          <div className="metrics-row">
            <div className="mini"><div className="v">{Math.round(Math.max(...live.data.points.map((p) => p.p50)) * 100)}%</div><div className="l">peak median solar output per kWp</div></div>
            <div className="mini"><div className="v">{Math.round(Math.max(...live.data.points.map((p) => p.p90)) * 100)}%</div><div className="l">peak sunny-case output per kWp</div></div>
            <div className="mini"><div className="v">{live.data.points.length} × 15 min</div><div className="l">intervals from {live.data.weather_source}</div></div>
          </div>
        )}
        {liveWarn.loading && <div className="loading">Checking the live forecast against the feeder model…</div>}
        {liveWarn.error && <div className="muted">Live warning unavailable: {liveWarn.error}</div>}
        {liveWarn.data && (
          <div className="warn-grid" style={{ marginTop: 12 }}>
            <div className="warn-case">
              <div className="muted">Tomorrow's {liveWarn.data.risk_band} risk case</div>
              <div className="v">{duration(liveWarn.data.predicted.violation_steps)} unsafe</div>
              <div className="muted">highest {volts(liveWarn.data.predicted.max_vm_pu)} V · starts around {liveWarn.data.predicted.first_unsafe ?? '—'}</div>
            </div>
            <div className="warn-case">
              <div className="muted">Interpretation</div>
              <div className="sub" style={{ marginTop: 8 }}>Demand uses the same-calendar-day CEEW Mathura proxy ({niceDate(liveWarn.data.demand_proxy_date)}); tomorrow's actual is intentionally not claimed before it occurs.</div>
            </div>
          </div>
        )}
      </div>
      <div className="card">
        <h2>Early warning for {warn.data ? niceDate(warn.data.date) : '…'}, with solar on every home</h2>
        <p className="sub">
          Left: what the AI predicted the day before. Right: an independent ERA5/PVWatts reference simulation, not measured panel output.
          {warn.data && ` Home electricity use is taken from the same calendar day in 2019 (${niceDate(warn.data.demand_proxy_date)}), the latest real meter data available.`}
        </p>
        {warn.data && (
          <div className="warn-grid">
            {(['p50', 'p90', 'actual'] as const).map((k) => {
              const c = warn.data!.cases[k]
              return (
                <div key={k} className={`warn-case ${k === 'actual' ? 'actual' : ''}`}>
                  <div className="muted">{k === 'p50' ? 'AI prediction (most likely)' : k === 'p90' ? 'AI prediction (sunny case)' : 'ERA5/PVWatts reference simulation'}</div>
                  <div className="v">{duration(c.violation_steps)} unsafe</div>
                  <div className="muted">highest {volts(c.max_vm_pu)} V · starts around {c.first_unsafe ?? '—'}</div>
                </div>
              )
            })}
          </div>
        )}
        {warn.loading && <div className="loading">Running the forecast through the street…</div>}
      </div>

      <div className="card">
        <h2>Prediction vs reality, on the street</h2>
        <p className="sub">
          Left: the street as our AI predicted it the day before. Right: the street on the real day. Press play: if the AI is
          right, the two maps turn red at the same times.
        </p>
        {sim.loading && <div className="loading">Replaying the predicted and the real day…</div>}
        {sim.data && grid.data && (
          <TwinSim sim={sim.data} grid={grid.data} leftTitle="AI prediction (made the day before)" rightTitle="ERA5/PVWatts reference"
            rightTone="neutral"
            doing={(real, predicted) => predicted.pv_kw > 1 || real.pv_kw > 1
              ? `the AI predicted ${Math.round(predicted.pv_kw)} kW; the ERA5/PVWatts reference estimated ${Math.round(real.pv_kw)} kW.`
              : 'no sun, so both days depend only on the voltage coming from the grid.'} />
        )}
      </div>

      <div className="split">
        <div className="card">
          <h2>Solar forecast for one home's 3 kW panels · 15 May 2025</h2>
          <p className="sub">The solid line is the AI's prediction; the dashed line is what the panels really produced.</p>
          {solar.data && <BandChart f={solar.data} scale={3} unit="kW" />}
          {metrics.data && <Scores m={metrics.data.solar} />}
        </div>
        <div className="card">
          <h2>Electricity use of an average home · 20 Nov 2019</h2>
          <p className="sub">Predicted from the home's own history and the temperature, then compared with its real meter.</p>
          {demand.data && <BandChart f={demand.data} scale={1000} unit="W" />}
          {metrics.data && <Scores m={metrics.data.demand} />}
        </div>
      </div>
    </div>
  )
}
