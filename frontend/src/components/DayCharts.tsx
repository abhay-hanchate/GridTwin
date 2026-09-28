import {
  Area, AreaChart, CartesianGrid, Legend, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { RunResult } from '../types'

const hhmm = (t: string) => t.slice(-5)

export function VoltageDayChart({ run, cursor }: { run: RunResult; cursor: string }) {
  const data = run.steps.map((s) => ({ t: hhmm(s.t), max: s.max_vm_pu, min: s.min_vm_pu, upstream: s.upstream_vm_pu }))
  const { vm_min_pu: lo, vm_max_pu: hi } = run.limits
  return (
    <ResponsiveContainer width="100%" height={230}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
        <CartesianGrid stroke="#e8ebe6" vertical={false} />
        <ReferenceArea y1={hi} y2={1.2} fill="#c8412b" fillOpacity={0.07} />
        <ReferenceArea y1={0.8} y2={lo} fill="#3f6fd8" fillOpacity={0.06} />
        <XAxis dataKey="t" interval={11} tick={{ fontSize: 11 }} />
        <YAxis domain={[0.85, 1.2]} ticks={[0.85, 0.9, 0.95, 1, 1.05, 1.1, 1.15, 1.2]}
          tick={{ fontSize: 11 }} tickFormatter={(v) => v.toFixed(2)} />
        <Tooltip formatter={(v) => (typeof v === 'number' ? `${v.toFixed(3)} pu (${Math.round(v * 230)} V)` : v)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <ReferenceLine y={hi} stroke="#c8412b" strokeDasharray="4 4" label={{ value: `limit ${hi}`, fontSize: 11, fill: '#c8412b', position: 'insideTopLeft' }} />
        <ReferenceLine y={lo} stroke="#3f6fd8" strokeDasharray="4 4" />
        <ReferenceLine x={hhmm(cursor)} stroke="#16201d" strokeOpacity={0.4} />
        <Line isAnimationActive={false} type="monotone" dataKey="max" name="Highest house voltage" stroke="#c8412b" dot={false} strokeWidth={2} />
        <Line isAnimationActive={false} type="monotone" dataKey="min" name="Lowest house voltage" stroke="#3f6fd8" dot={false} strokeWidth={2} />
        <Line isAnimationActive={false} type="monotone" dataKey="upstream" name="Upstream (measured)" stroke="#7a8581" dot={false} strokeDasharray="3 3" strokeWidth={1.4} />
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
        <Area isAnimationActive={false} type="monotone" dataKey="solar" name="Rooftop solar" stroke="#e8a317" fill="#e8a317" fillOpacity={0.25} />
        <Area isAnimationActive={false} type="monotone" dataKey="demand" name="Household demand" stroke="#5b6ee1" fill="#5b6ee1" fillOpacity={0.15} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
