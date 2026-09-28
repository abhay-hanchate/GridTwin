import { useEffect, useMemo, useState } from 'react'
import { useApi, volts } from '../api'
import type { GridTopology, RunResult, ScenarioId } from '../types'
import { PowerDayChart, VoltageDayChart } from './DayCharts'
import GridMap from './GridMap'

export default function GridView({ scenario }: { scenario: ScenarioId }) {
  const run = useApi<RunResult>(`/api/run?scenario=${scenario}`)
  const grid = useApi<GridTopology>(`/api/grid?scenario=${scenario}`)
  const [idx, setIdx] = useState(44)            // 11:00, the solar peak
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setIdx((i) => (i + 1) % 96), 180)
    return () => clearInterval(id)
  }, [playing])

  const step = run.data?.steps[idx]
  const counts = useMemo(() => {
    if (!step) return { over: 0, under: 0 }
    const buses = (type: string) => new Set(step.violations.filter((v) => v.type === type).map((v) => v.id)).size
    return { over: buses('overvoltage'), under: buses('undervoltage') }
  }, [step])

  if (run.loading || grid.loading) return <div className="loading">Simulating the feeder…</div>
  if (run.error || grid.error) return <div className="error">{run.error ?? grid.error}</div>
  if (!run.data || !grid.data || !step) return null
  const r = run.data
  const s = r.summary

  return (
    <>
      <div className="kpis">
        <div className={`card kpi ${s.violation_steps ? 'alert' : ''}`}>
          <div className="kpi-label">Unsafe time</div>
          <div className="kpi-value">{s.violation_steps} / 96</div>
          <div className="kpi-note">15-minute steps outside ±{r.band}% on {r.date}</div>
        </div>
        <div className={`card kpi ${s.violation_steps_from_solar ? 'alert' : ''}`}>
          <div className="kpi-label">Caused by solar</div>
          <div className="kpi-value">{s.violation_steps_from_solar}</div>
          <div className="kpi-note">{s.violation_steps_without_solar} steps are unsafe even with no solar</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Peak voltage</div>
          <div className="kpi-value">{volts(s.max_vm_pu)} V</div>
          <div className="kpi-note">{s.max_vm_pu.toFixed(3)} pu · limit {volts(r.limits.vm_max_pu)} V</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Solar generated</div>
          <div className="kpi-value">{Math.round(s.pv_kwh)} kWh</div>
          <div className="kpi-note">{Math.round(r.pv_share * 99)} of 99 homes · 3 kW each</div>
        </div>
      </div>

      <div className="split">
        <div className="card">
          <h2>Feeder map</h2>
          <p className="sub">99 homes on a 250 kVA transformer. Colour = voltage at each house; ring = rooftop solar; line width = loading.</p>
          <GridMap grid={grid.data} step={step} limits={r.limits} />
          <div className="legend">
            <span><i style={{ background: 'var(--safe)' }} />Safe</span>
            <span><i style={{ background: 'var(--near)' }} />Within 2% of a limit</span>
            <span><i style={{ background: 'var(--unsafe)' }} />Over-voltage</span>
            <span><i style={{ background: 'var(--under)' }} />Under-voltage</span>
            <span><i style={{ background: 'transparent', border: '2px solid var(--solar)' }} />Rooftop solar</span>
          </div>
          <div className="player">
            <button className="play" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play the day'}>
              {playing ? '❚❚' : '▶'}
            </button>
            <input type="range" min={0} max={95} value={idx} aria-label="Time of day"
              onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)) }} />
            <span className="clock">{step.t.slice(-5)}</span>
          </div>
          <div className={`step-status ${step.violations.length ? 'bad' : 'ok'}`}>
            {step.violations.length
              ? `${counts.over} of 96 connection points over-voltage, ${counts.under} under-voltage · highest ${volts(step.max_vm_pu)} V`
              : `Every connection point within limits · ${volts(step.min_vm_pu)}–${volts(step.max_vm_pu)} V`}
            {' · '}solar {step.pv_kw.toFixed(0)} kW, demand {step.load_kw.toFixed(0)} kW
          </div>
        </div>
        <div className="stack">
          <div className="card">
            <h2>Voltage through the day</h2>
            <p className="sub">Shaded bands are outside the ±{r.band}% limit. Dashed grey is the measured upstream voltage.</p>
            <VoltageDayChart run={r} cursor={step.t} />
          </div>
          <div className="card">
            <h2>Solar vs demand</h2>
            <p className="sub">When solar exceeds demand, power flows back up the wires and pushes voltage up.</p>
            <PowerDayChart run={r} cursor={step.t} />
          </div>
        </div>
      </div>

      <div className="provenance">
        {Object.entries(r.provenance).map(([k, v]) => (
          <span key={k} className="chip"><b>{k}</b>{v}</span>
        ))}
      </div>
    </>
  )
}
