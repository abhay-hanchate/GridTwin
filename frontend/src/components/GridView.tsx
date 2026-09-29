import { useEffect, useMemo, useState } from 'react'
import { useApi, volts } from '../api'
import { duration, SCENARIO_TEXT } from '../plain'
import type { GridTopology, RunResult, ScenarioId } from '../types'
import { PowerDayChart, VoltageDayChart } from './DayCharts'
import GridMap from './GridMap'

const PROVENANCE_TEXT: Record<string, string> = {
  load: 'Electricity use: measured by real smart meters in Mathura homes',
  voltage: 'Voltage arriving at the street: measured by the same meters',
  pv: 'Solar output: calculated from real Mathura weather',
  grid: 'Street wiring: public benchmark street, adapted to Indian overhead wires',
}

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

  if (run.loading || grid.loading) return <div className="loading" role="status">Simulating the street…</div>
  if (run.error || grid.error) return <div className="error" role="alert">{run.error ?? grid.error}</div>
  if (!run.data || !grid.data || !step) return null
  const r = run.data
  const s = r.summary
  const hi = volts(r.limits.vm_max_pu)
  const lo = volts(r.limits.vm_min_pu)

  return (
    <>
      <p className="how">
        <b>{SCENARIO_TEXT[scenario].long}.</b> We replay one real day (15 May 2019) and check the voltage at every point
        on the street's wire every 15 minutes. Safe means between {lo} V and {hi} V.
      </p>
      <div className="kpis">
        <div className={`card kpi ${s.violation_steps ? 'alert' : ''}`}>
          <div className="kpi-label">Unsafe today</div>
          <div className="kpi-value">{duration(s.violation_steps)}</div>
          <div className="kpi-note">time some homes were outside {lo}–{hi} V</div>
        </div>
        <div className={`card kpi ${s.violation_steps_from_solar > 0 ? 'alert' : ''}`}>
          <div className="kpi-label">Of which caused by solar</div>
          <div className="kpi-value">{duration(Math.max(s.violation_steps_from_solar, 0))}</div>
          <div className="kpi-note">the other {duration(s.violation_steps_without_solar)} happens even without solar</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Highest voltage</div>
          <div className="kpi-value">{volts(s.max_vm_pu)} V</div>
          <div className="kpi-note">safe limit is {hi} V</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Solar produced</div>
          <div className="kpi-value">{Math.round(s.pv_kwh)} kWh</div>
          <div className="kpi-note">{Math.round(r.pv_share * 99)} of 99 homes, 3 kW panels each</div>
        </div>
      </div>

      <div className="split">
        <div className="card">
          <h2>The street, minute by minute</h2>
          <p className="sub">
            Each dot is a point on the wire (almost all are homes); T is the transformer. Press play to watch a day:
            dots turn red when voltage there goes above {hi} V.
          </p>
          <GridMap grid={grid.data} step={step} limits={r.limits} />
          <div className="legend">
            <span><i style={{ background: 'var(--safe)' }} />Safe</span>
            <span><i style={{ background: 'var(--near)' }} />Close to the limit</span>
            <span><i style={{ background: 'var(--unsafe)' }} />Too high</span>
            <span><i style={{ background: 'var(--under)' }} />Too low</span>
            <span><i style={{ background: 'transparent', border: '2px solid var(--solar)' }} />Home with solar</span>
          </div>
          <div className="player">
            <button className="play" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play the day'}>
              {playing ? '❚❚' : '▶'}
            </button>
            <input type="range" min={0} max={95} value={idx} aria-label="Time of day" aria-valuetext={step.t.slice(-5)}
              onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)) }} />
            <span className="clock">{step.t.slice(-5)}</span>
          </div>
          <div className={`step-status ${step.violations.length ? 'bad' : 'ok'}`}>
            <b>At {step.t.slice(-5)}:</b>{' '}
            {step.violations.length
              ? `${counts.over ? `${counts.over} of 96 points are too high` : ''}${counts.over && counts.under ? ', ' : ''}${counts.under ? `${counts.under} too low` : ''} (highest ${volts(step.max_vm_pu)} V).`
              : `every point is safe (${volts(step.min_vm_pu)}–${volts(step.max_vm_pu)} V).`}
            {' '}Solar is making {step.pv_kw.toFixed(0)} kW while homes use {step.load_kw.toFixed(0)} kW.
          </div>
        </div>
        <div className="stack">
          <div className="card">
            <h2>Voltage through the day</h2>
            <p className="sub">
              Red line: the highest voltage anywhere on the street. Above the dashed {hi} V line is unsafe (shaded).
            </p>
            <VoltageDayChart run={r} cursor={step.t} />
          </div>
          <div className="card">
            <h2>Why it happens: solar vs what homes use</h2>
            <p className="sub">When the orange area is bigger than the blue, the extra solar flows back into the wire and pushes voltage up.</p>
            <PowerDayChart run={r} cursor={step.t} />
          </div>
        </div>
      </div>

      <div className="provenance">
        {Object.keys(r.provenance).map((k) => (
          <span key={k} className="chip">{PROVENANCE_TEXT[k] ?? r.provenance[k]}</span>
        ))}
      </div>
    </>
  )
}
