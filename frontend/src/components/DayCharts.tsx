import {
  Area, AreaChart, CartesianGrid, Legend, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { RunResult } from '../types'

const hhmm = (t: string) => t.slice(-5)
const V = (pu: number) => Math.round(pu * 230)

export function VoltageDayChart({ run, cursor }: { run: RunResult; cursor: string }) {
  const data = run.steps.map((s) => ({ t: hhmm(s.t), max: V(s.max_vm_pu), min: V(s.min_vm_pu) }))
  const hi = V(run.limits.vm_max_pu)
  const lo = V(run.limits.vm_min_pu)
  return (
    <ResponsiveContainer width="100%" height={230}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -4, bottom: 0 }}>
        <CartesianGrid stroke="#e8ebe6" vertical={false} />
        <ReferenceArea y1={hi} y2={275} fill="#c8412b" fillOpacity={0.08} />
        <ReferenceArea y1={195} y2={lo} fill="#3f6fd8" fillOpacity={0.06} />
        <XAxis dataKey="t" interval={11} tick={{ fontSize: 11 }} />
        <YAxis domain={[195, 275]} ticks={[200, 210, 220, 230, 240, 250, 260, 270]} unit=" V" width={58} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v) => `${v} V`} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <ReferenceLine y={hi} stroke="#c8412b" strokeDasharray="4 4"
          label={{ value: `safe limit ${hi} V`, fontSize: 11, fill: '#c8412b', position: 'insideBottomLeft' }} />
        <ReferenceLine y={lo} stroke="#3f6fd8" strokeDasharray="4 4" />
        <ReferenceLine x={hhmm(cursor)} stroke="#16201d" strokeOpacity={0.4} />
        <Line isAnimationActive={false} type="monotone" dataKey="max" name="Highest voltage on the street" stroke="#c8412b" dot={false} strokeWidth={2} />
        <Line isAnimationActive={false} type="monotone" dataKey="min" name="Lowest voltage on the street" stroke="#3f6fd8" dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function PowerDayChart({ run, cursor }: { run: RunResult; cursor: string }) {
  const data = run.steps.map((s) => ({ t: hhmm(s.t), solar: s.pv_kw, demand: s.load_kw }))
  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
        <CartesianGrid stroke="#e8ebe6" vertical={false} />
        <XAxis dataKey="t" interval={11} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} unit=" kW" width={64} />
        <Tooltip formatter={(v) => (typeof v === 'number' ? `${v.toFixed(1)} kW` : v)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <ReferenceLine x={hhmm(cursor)} stroke="#16201d" strokeOpacity={0.4} />
        <Area isAnimationActive={false} type="monotone" dataKey="solar" name="Solar produced by the street" stroke="#e8a317" fill="#e8a317" fillOpacity={0.25} />
        <Area isAnimationActive={false} type="monotone" dataKey="demand" name="Electricity the homes use" stroke="#5b6ee1" fill="#5b6ee1" fillOpacity={0.15} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
