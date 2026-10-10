import { memo, type ReactNode } from 'react'
import type { StreetLayout } from '../../api/v2types'
import { CONDUCTORS, OFFSET, geometry, wirePath, type Conductor, type Flow, type HomeView, type Marker } from './geometry'

type Props = {
  layout: StreetLayout
  homes: HomeView[]
  /** [line][conductor] flow; without it the wires are drawn still. */
  flows?: Record<number, Partial<Record<Conductor, Flow>>>
  markers?: Marker[]
  selectedHome?: number | null
  onHome?: (home: number) => void
  selectedNode?: number | null
  onNode?: (node: number) => void
  trafoLabel: string
  trafoSub?: string
  label: string
  children?: ReactNode
}

const HOUSE = 'M-6,1 L0,-5 L6,1 V7 H-6 Z'

/** The street as a one-line diagram: transformer at the left, four conductors (phases A, B, C and the neutral N)
 *  along every wire, and each home hanging off its own phase. Flows, if given, animate along the conductors. */
function StreetMap({ layout, homes, flows, markers = [], selectedHome, onHome, selectedNode, onNode, trafoLabel, trafoSub, label, children }: Props) {
  const { pos, width, height } = geometry(layout)
  const root = pos.get(layout.root)!
  const atNode = new Map<number, number[]>()
  homes.forEach((h, i) => atNode.set(h.node, [...(atNode.get(h.node) ?? []), i]))
  return (
    <svg className="street-svg" viewBox={`0 0 ${width} ${height}`} width="100%" style={{ minWidth: Math.min(width, 980) }}
      role="img" aria-label={label}>
      {/* transformer and the LV busbar that every feeder leaves from */}
      {(() => {
        const rows = layout.lines.filter((l) => l.from === layout.root).map((l) => pos.get(l.to)!.y)
        const top = Math.min(root.y, ...rows) - 14
        const bottom = Math.max(root.y, ...rows) + 14
        return (
          <g>
            {CONDUCTORS.map((c) => (
              <path key={c} className={`wire wire-${c.toLowerCase()}`} d={`M${root.x - 44},${root.y + OFFSET[c]}H${root.x - 6}`} strokeWidth={2.4} />
            ))}
            <rect className="bus" x={root.x - 6} y={top} width={8} height={bottom - top} rx={3} />
            <text className="grid-label" x={root.x + 6} y={bottom + 16}>LV</text>
          </g>
        )
      })()}
      <rect className="trafo-box" x={root.x - 120} y={root.y - 22} width={76} height={44} rx={11} />
      <text className="trafo-text" x={root.x - 82} y={root.y + 4} textAnchor="middle">{trafoLabel}</text>
      {trafoSub && <text className="trafo-sub" x={root.x - 82} y={root.y + 40} textAnchor="middle">{trafoSub}</text>}

      {/* the four conductors of every segment: a faint base line, and the moving flow on top */}
      {layout.lines.map((ln) => {
        const p = pos.get(ln.from)!
        const c = pos.get(ln.to)!
        return CONDUCTORS.map((cd) => {
          const d = wirePath(p, c, OFFSET[cd], ln.from === layout.root)
          const f = flows?.[ln.line]?.[cd]
          const mag = f ? Math.abs(f.kw) : 0
          const idle = !f || mag < 0.05
          const dur = idle ? 0 : Math.max(0.28, 2.6 / (0.45 + Math.sqrt(mag)))
          return (
            <g key={`${ln.line}-${cd}`}>
              <path className={`wire wire-base wire-${cd.toLowerCase()}`} d={d} strokeWidth={cd === 'N' ? 1.2 : 1.6} />
              {flows && (
                <path className={`wire flow wire-${cd.toLowerCase()} ${idle ? 'idle' : f.kw < 0 ? 'back' : ''}`} d={d}
                  strokeWidth={Math.min(4.4, 2 + mag / 6)} style={idle ? undefined : { animationDuration: `${dur.toFixed(2)}s` }} />
              )}
            </g>
          )
        })
      })}

      {/* homes: a drop from their phase conductor, the house coloured by its voltage, a panel if it has solar */}
      {[...atNode.entries()].map(([node, list]) => {
        const p = pos.get(node)
        if (!p) return null
        return list.map((h, k) => {
          const home = homes[h]
          const up = k % 2 === 0
          const hy = up ? p.y - 26 : p.y + 26
          const wy = p.y + OFFSET[home.phase]
          const hx = p.x + (k > 1 ? 9 : 0)
          return (
            <g key={h} data-home={h} onClick={onHome ? () => onHome(h) : undefined}>
              <line className={`drop wire-${home.phase.toLowerCase()}`} x1={hx} y1={wy} x2={hx} y2={up ? hy + 6 : hy - 5} />
              <path className={`home ${home.cls} ${selectedHome === h ? 'sel' : ''}`} d={HOUSE} transform={`translate(${hx},${hy})`}>
                <title>{home.title}</title>
              </path>
              {home.kwp > 0 && <rect className="panel" x={hx - 4} y={hy - 5.2} width={8} height={2.2} rx={0.8}
                transform={`rotate(${up ? 0 : 0} ${hx} ${hy})`} />}
            </g>
          )
        })
      })}

      {/* places to click (planning) */}
      {onNode && layout.nodes.map((n) => {
        const p = pos.get(n.id)!
        return <circle key={n.id} className={`node-pick ${selectedNode === n.id ? 'sel' : ''}`} cx={p.x} cy={p.y} r={11}
          onClick={() => onNode(n.id)}><title>{n.id}</title></circle>
      })}

      {markers.map((m) => {
        const p = pos.get(m.node)
        if (!p) return null
        return m.kind === 'probe' ? (
          <g key={`p${m.node}${m.text}`}>
            <circle className="probe" cx={p.x} cy={p.y} r={8} />
            {/* labels lean inwards so they never run off the edge of the map */}
            <text className="probe-label" x={p.x > width / 2 ? p.x + 12 : p.x - 12} y={p.y + 46}
              textAnchor={p.x > width / 2 ? 'end' : 'start'}>{m.text}</text>
          </g>
        ) : (
          <g key={`m${m.node}${m.text}`}>
            <circle className="marker" cx={p.x} cy={p.y} r={10} />
            <text className="marker-text" x={p.x} y={p.y + 3.5} textAnchor="middle">{m.text}</text>
          </g>
        )
      })}
      {children}
    </svg>
  )
}

export default memo(StreetMap)
