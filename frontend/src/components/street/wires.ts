import type { StreetLayout, StreetRun } from '../../api/v2types'
import type { Conductor, Flow } from './geometry'

export type WireFlow = Partial<Record<Conductor, Flow>>
type RunLines = Pick<StreetRun, 'line_phase_kw' | 'line_neutral_a'> & { line_ends?: number[][] }

const key = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`)

/** [parent, child] of every line of the run's own network; older payloads without it share the layout's numbering. */
function ends(layout: StreetLayout, run: RunLines): number[][] {
  if (run.line_ends) return run.line_ends
  const out: number[][] = []
  layout.lines.forEach((ln) => { out[ln.line] = [ln.from, ln.to] })
  return out
}

/** A fix that switches the topology (opens a wire, closes a tie) re-numbers the lines, so the run's flows are matched
 *  to the drawn wires by their end nodes. Drawn wires the run no longer has are `open`; run wires the drawing lacks
 *  are `ties`. Positive kW is towards the homes in the run's own tree, flipped where the drawing runs the other way. */
export function matchWires(layout: StreetLayout, run: RunLines, step: number) {
  const lp = run.line_phase_kw[step]
  const total = lp.reduce((a, r) => a + r[0] + r[1] + r[2], 0)
  const flowOf = (i: number, sign: number): WireFlow => {
    const r = lp[i]
    // The neutral returns the imbalance to the transformer's star point: back when the street draws power,
    // outwards when it exports. Shown in kW-equivalent at 230 V so its speed compares with the phases.
    const nKw = (run.line_neutral_a[step][i] * 230) / 1000
    return { A: { kw: sign * r[0] }, B: { kw: sign * r[1] }, C: { kw: sign * r[2] }, N: { kw: total >= 0 ? -nKw : nKw } }
  }
  const runEnds = ends(layout, run)
  const byPair = new Map(runEnds.map((e, i) => [key(e[0], e[1]), i]))
  const flows: Record<number, WireFlow> = {}
  const open = new Set<number>()
  const drawn = new Set<string>()
  layout.lines.forEach((ln) => {
    drawn.add(key(ln.from, ln.to))
    const i = byPair.get(key(ln.from, ln.to))
    if (i === undefined) open.add(ln.line)
    else flows[ln.line] = flowOf(i, runEnds[i][0] === ln.from ? 1 : -1)
  })
  const ties = runEnds.flatMap((e, i) => (drawn.has(key(e[0], e[1])) ? [] : [{ from: e[0], to: e[1], flow: flowOf(i, 1) }]))
  return { flows, open, ties }
}

/** Per-phase kW on the wires that leave the transformer, in the run's own network. */
export function rootPhaseKw(layout: StreetLayout, run: RunLines, step: number): [number, number, number] {
  const out: [number, number, number] = [0, 0, 0]
  ends(layout, run).forEach((e, i) => {
    if (e[0] === layout.root) for (let k = 0; k < 3; k++) out[k] += run.line_phase_kw[step][i][k]
  })
  return out
}
