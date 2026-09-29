import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { volts } from '../api'
import type { GridTopology, SimResult, SimSide, SimStep, Step } from '../types'
import GridMap from './GridMap'

interface Props {
  sim: SimResult
  grid: GridTopology
  leftTitle: string
  rightTitle: string
  rightTone?: 'good' | 'neutral'
  /** One plain sentence about what the fix (or forecast) is doing at this moment. */
  doing?: (right: SimStep, left: SimStep) => string
  startIdx?: number
}

/** Adapt one row of the compact matrix to the Step shape GridMap draws. */
function asStep(side: SimSide, busIds: number[], idx: number, t: string): Step | null {
  const row = side.vm[idx]
  if (!row) return null
  const bus_vm_pu: Record<string, number> = {}
  busIds.forEach((b, i) => { bus_vm_pu[String(b)] = row[i] })
  const s = side.steps[idx]
  return { t, max_vm_pu: s.max_vm_pu, min_vm_pu: s.min_vm_pu, trafo_loading_pct: 0, pv_kw: s.pv_kw, load_kw: s.load_kw,
    upstream_vm_pu: 0, violations: [], bus_vm_pu, line_loading_pct: {} }
}

function status(side: SimSide, idx: number, hi: number, lo: number) {
  const row = side.vm[idx]
  if (!row) return { bad: true, text: 'Calculation did not converge at this step' }
  const over = row.filter((v) => v > hi).length
  const under = row.filter((v) => v < lo).length
  const s = side.steps[idx]
  if (!over && !under) return { bad: false, text: `All 96 points safe · highest ${volts(s.max_vm_pu)} V` }
  const parts = [over ? `${over} points too high` : '', under ? `${under} too low` : ''].filter(Boolean)
  return { bad: true, text: `${parts.join(', ')} · highest ${volts(s.max_vm_pu)} V` }
}

export default function TwinSim({ sim, grid, leftTitle, rightTitle, rightTone = 'good', doing, startIdx = 44 }: Props) {
  const [idx, setIdx] = useState(startIdx)
  const [playing, setPlaying] = useState(false)
  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setIdx((i) => (i + 1) % sim.times.length), 200)
    return () => clearInterval(id)
  }, [playing, sim.times.length])

  const { vm_min_pu: lo, vm_max_pu: hi } = sim.limits
  const t = sim.times[idx]
  const left = asStep(sim.before, sim.bus_ids, idx, t)
  const right = asStep(sim.after, sim.bus_ids, idx, t)
  const ls = status(sim.before, idx, hi, lo)
  const rs = status(sim.after, idx, hi, lo)

  const chart = useMemo(() => sim.times.map((time, i) => ({
    t: time,
    left: Math.round(sim.before.steps[i].max_vm_pu * 230),
    right: Math.round(sim.after.steps[i].max_vm_pu * 230),
  })), [sim])

  return (
    <div className="twin">
      <div className="player twin-player">
        <button className="play" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play the day'}>
          {playing ? '❚❚' : '▶'}
        </button>
        <input type="range" min={0} max={sim.times.length - 1} value={idx} aria-label="Time of day" aria-valuetext={t}
          onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)) }} />
        <span className="clock">{t}</span>
      </div>

      <div className="twin-maps">
        <div className="twin-side">
          <div className="twin-title">{leftTitle}</div>
          {left && <GridMap grid={grid} step={left} limits={sim.limits} />}
          <div className={`step-status ${ls.bad ? 'bad' : 'ok'}`}>{ls.text}</div>
        </div>
        <div className="twin-side">
          <div className={`twin-title ${rightTone}`}>{rightTitle}</div>
          {right && <GridMap grid={grid} step={right} limits={sim.limits} />}
          <div className={`step-status ${rs.bad ? 'bad' : 'ok'}`}>{rs.text}</div>
        </div>
      </div>

      {doing && <div className="doing"><b>At {t}:</b> {doing(sim.after.steps[idx], sim.before.steps[idx])}</div>}

      <div className="twin-chart">
        <div className="muted" style={{ marginBottom: 4 }}>Highest voltage on the street through the day</div>
        <ResponsiveContainer width="100%" height={210}>
          <LineChart data={chart} margin={{ top: 8, right: 12, left: -4, bottom: 0 }}>
            <CartesianGrid stroke="#e8ebe6" vertical={false} />
            <ReferenceArea y1={Math.round(hi * 230)} y2={275} fill="#c8412b" fillOpacity={0.08} />
            <XAxis dataKey="t" interval={11} tick={{ fontSize: 11 }} />
            <YAxis domain={[215, 275]} ticks={[220, 230, 240, 250, 260, 270]} unit=" V" width={58} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => `${v} V`} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <ReferenceLine y={Math.round(hi * 230)} stroke="#c8412b" strokeDasharray="4 4"
              label={{ value: `safe limit ${Math.round(hi * 230)} V`, fontSize: 11, fill: '#c8412b', position: 'insideBottomLeft' }} />
            <ReferenceLine x={t} stroke="#16201d" strokeOpacity={0.45} />
            <Line isAnimationActive={false} dataKey="left" name={leftTitle} stroke="#c8412b" strokeDasharray="5 4" dot={false} strokeWidth={2} />
            <Line isAnimationActive={false} dataKey="right" name={rightTitle} stroke={rightTone === 'good' ? '#2b8a6e' : '#16201d'} dot={false} strokeWidth={2.4} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
