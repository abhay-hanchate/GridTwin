import type { Street, StreetRun } from '../../api/v2types'

/** One quarter hour of the street's power balance, all in kW: grid + solar = homes + losses. */
export interface Balance {
  solar: number          // delivered by the rooftop panels
  homes: number          // what the homes use
  losses: number         // heat in the wires and the transformer
  grid: number           // through the transformer: + drawn from the grid, - sent back
}

export const PHASES = ['A', 'B', 'C'] as const
const PH = { A: 0, B: 1, C: 2 } as const
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0)

/** The feeders leaving the transformer: their phase flows add up to the street's net flow before losses. */
export const rootLines = (s: Street) => s.layout.lines.filter((l) => l.from === s.layout.root).map((l) => l.line)

/** The balance at step `k`. The wire flows are the homes' net power with losses left out, so
 *  losses = grid - wire flow and homes = wire flow + solar. Checked against the solver's own losses (55.2 against
 *  55.1 kWh over a day). */
export function balance(s: Street, run: StreetRun, k: number): Balance {
  const solar = run.solar_kw[k]
  const grid = run.trafo_kw[k]
  const wire = sum(rootLines(s).map((l) => sum(run.line_phase_kw[k][l])))
  return { solar, grid, homes: Math.max(0, wire + solar), losses: Math.max(0, grid - wire) }
}

/** The per-phase flow at the transformer (kW, + towards the homes), from the wire flows: losses not included. */
export function phaseKw(s: Street, run: StreetRun, k: number): [number, number, number] {
  const roots = rootLines(s)
  return [0, 1, 2].map((p) => sum(roots.map((l) => run.line_phase_kw[k][l][p]))) as [number, number, number]
}

/** Each home through the day, kW per [step][home]. */
export interface HomeFlows {
  solar: number[][]
  demand: number[][]
  /** demand - solar: + drawn from its phase, - sent back into it */
  net: number[][]
  /** homes that share a connection point and a phase with another home: their demand is the pair's, split evenly */
  shared: boolean[]
}

/** Every home's solar, demand and net power, from what /street already carries. The model has one irradiance for
 *  the street, so a home's solar is the street's solar times its share of the panels. Its net power is what flows
 *  into its node on its phase minus what flows on (checked against the engine: within 0.1 kW, the rounding of the
 *  flows). Demand is net plus solar. */
export function homeFlows(s: Street, run: StreetRun): HomeFlows {
  const into = new Map(s.layout.lines.map((l) => [l.to, l.line]))
  const onward = new Map<number, number[]>()
  s.layout.lines.forEach((l) => onward.set(l.from, [...(onward.get(l.from) ?? []), l.line]))
  const kwpTotal = sum(s.homes.map((h) => h.kwp)) || 1
  const groups = new Map<string, number[]>()
  s.homes.forEach((h, i) => {
    const key = `${h.node}${run.home_phase[i]}`
    groups.set(key, [...(groups.get(key) ?? []), i])
  })
  const T = run.solar_kw.length
  const H = s.homes.length
  const solar = Array.from({ length: T }, (_, k) => s.homes.map((h) => (run.solar_kw[k] * h.kwp) / kwpTotal))
  const net = Array.from({ length: T }, () => new Array<number>(H).fill(0))
  const demand = Array.from({ length: T }, () => new Array<number>(H).fill(0))
  const shared = new Array<boolean>(H).fill(false)
  for (const ids of groups.values()) {
    const node = s.homes[ids[0]].node
    const p = PH[run.home_phase[ids[0]]]
    const line = into.get(node)
    if (ids.length > 1) ids.forEach((i) => { shared[i] = true })
    for (let k = 0; k < T; k++) {
      const lp = run.line_phase_kw[k]
      const here = line === undefined ? 0 : lp[line][p] - sum((onward.get(node) ?? []).map((l) => lp[l][p]))
      const each = Math.max(0, here + sum(ids.map((i) => solar[k][i]))) / ids.length
      ids.forEach((i) => { demand[k][i] = each; net[k][i] = each - solar[k][i] })
    }
  }
  return { solar, demand, net, shared }
}

/** Hops from the transformer to every node: how far along the street a home is. */
export function depth(s: Street): Map<number, number> {
  const kids = new Map<number, number[]>()
  s.layout.lines.forEach((l) => kids.set(l.from, [...(kids.get(l.from) ?? []), l.to]))
  const out = new Map([[s.layout.root, 0]])
  const queue = [s.layout.root]
  while (queue.length) {
    const n = queue.shift()!
    for (const c of kids.get(n) ?? []) if (!out.has(c)) { out.set(c, out.get(n)! + 1); queue.push(c) }
  }
  return out
}

/** The home nearest to `node` along the wires (on `phase` if given): the home a point of the network is shown at. */
export function nearestHome(s: Street, phases: readonly string[], node: number, phase?: string): number | null {
  const next = new Map<number, number[]>()
  s.layout.lines.forEach((l) => {
    next.set(l.from, [...(next.get(l.from) ?? []), l.to])
    next.set(l.to, [...(next.get(l.to) ?? []), l.from])
  })
  const seen = new Set([node])
  let ring = [node]
  while (ring.length) {
    const here = s.homes.findIndex((h, i) => ring.includes(h.node) && (!phase || phases[i] === phase))
    if (here >= 0) return here
    ring = ring.flatMap((n) => next.get(n) ?? []).filter((n) => !seen.has(n) && seen.add(n))
  }
  return null
}
