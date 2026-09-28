import { useMemo } from 'react'
import { volts } from '../api'
import type { GridTopology, Step } from '../types'

interface Props {
  grid: GridTopology
  step: Step
  limits: { vm_min_pu: number; vm_max_pu: number }
}

const W = 640
const H = 330
const PAD = 24

export function voltageColor(vm: number, lo: number, hi: number) {
  if (vm > hi) return 'var(--unsafe)'
  if (vm < lo) return 'var(--under)'
  if (vm > hi - 0.02 || vm < lo + 0.02) return 'var(--near)'
  return 'var(--safe)'
}

export default function GridMap({ grid, step, limits }: Props) {
  const pos = useMemo(() => {
    // Longitude degrees shrink with latitude, so scale them to keep true proportions. The feeder
    // runs north-south, so it is drawn rotated 90 degrees (north to the right) to fill the card.
    const k = Math.cos((grid.buses[0].y * Math.PI) / 180)
    const xs = grid.buses.map((b) => b.y)
    const ys = grid.buses.map((b) => -b.x * k)
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
    const s = Math.min((W - 2 * PAD) / (x1 - x0 || 1), (H - 2 * PAD) / (y1 - y0 || 1))
    const ox = (W - s * (x1 - x0)) / 2
    const oy = (H - s * (y1 - y0)) / 2
    const map = new Map<number, [number, number]>()
    grid.buses.forEach((b) => map.set(b.id, [ox + (b.y - x0) * s, H - (oy + (-b.x * k - y0) * s)]))
    return map
  }, [grid])

  const { vm_min_pu: lo, vm_max_pu: hi } = limits
  const trafo = pos.get(grid.trafo.lv_bus)

  return (
    <svg className="map-svg" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label={`Feeder map at ${step.t.slice(-5)}: bus voltages coloured against the ${lo}-${hi} per-unit band`}>
      <g stroke="#b9c2bb" strokeWidth={1.6}>
        {grid.lines.map((l) => {
          const a = pos.get(l.from)
          const b = pos.get(l.to)
          if (!a || !b) return null
          const loading = step.line_loading_pct?.[String(l.id)] ?? 0
          return <line key={l.id} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} strokeWidth={1.2 + loading / 25} />
        })}
      </g>
      {grid.buses.map((b) => {
        const p = pos.get(b.id)!
        const vm = step.bus_vm_pu?.[String(b.id)]
        if (vm === undefined) return null
        const color = voltageColor(vm, lo, hi)
        return (
          <g key={b.id}>
            {b.pv && <circle cx={p[0]} cy={p[1]} r={8} fill="none" stroke="var(--solar)" strokeWidth={1.8} />}
            <circle cx={p[0]} cy={p[1]} r={b.house ? 5 : 3} fill={color} stroke="#fff" strokeWidth={1}>
              <title>{`Bus ${b.id}: ${vm.toFixed(3)} pu (${volts(vm)} V)${b.pv ? ' · rooftop solar' : ''}`}</title>
            </circle>
          </g>
        )
      })}
      {trafo && (
        <g>
          <rect x={trafo[0] - 11} y={trafo[1] - 11} width={22} height={22} rx={5} fill="var(--ink)" />
          <text x={trafo[0]} y={trafo[1] + 4} textAnchor="middle" fontSize={11} fill="#fff" fontWeight={700}>T</text>
          <title>{`Transformer ${grid.trafo.sn_kva} kVA`}</title>
        </g>
      )}
    </svg>
  )
}
