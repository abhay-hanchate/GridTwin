import type { StreetLayout } from '../../api/v2types'

/** Shared geometry of the street schematic (StreetMap) and the types of what is drawn on it. */
export const DX = 30                      // one wire segment
export const DY = 96                      // one branch row
export const LEFT = 150                   // room for the transformer and the LV busbar
export const TOP = 54
export const WIRE_GAP = 5.2               // spacing of the four conductors
export const CONDUCTORS = ['A', 'B', 'C', 'N'] as const
export type Conductor = (typeof CONDUCTORS)[number]
export const OFFSET: Record<Conductor, number> = { A: -1.5 * WIRE_GAP, B: -0.5 * WIRE_GAP, C: 0.5 * WIRE_GAP, N: 1.5 * WIRE_GAP }

export interface Flow { kw: number }                    // positive = towards the homes
export interface HomeView { node: number; phase: 'A' | 'B' | 'C'; kwp: number; cls: string; title: string }
export interface Marker { node: number; text: string; label?: string; kind?: 'marker' | 'probe' }

export function geometry(layout: StreetLayout) {
  const pos = new Map(layout.nodes.map((n) => [n.id, { x: LEFT + n.x * DX, y: TOP + n.y * DY }]))
  const maxX = Math.max(...layout.nodes.map((n) => n.x))
  return { pos, width: LEFT + maxX * DX + 60, height: TOP + (layout.rows - 1) * DY + 62 }
}

/** The wire from parent to child for one conductor: along the parent's row, down at the half step, along the child's
 *  row. Heading right the conductor sits `o` above the centre; heading down it sits `o` to the right (left of travel). */
export function wirePath(p: { x: number; y: number }, c: { x: number; y: number }, o: number, fromBus = false): string {
  if (p.y === c.y) return `M${p.x},${p.y + o}H${c.x}`
  if (fromBus) return `M${p.x},${c.y + o}H${c.x}`        // a feeder leaves the LV busbar on its own row
  const mid = p.x + DX / 2
  return `M${p.x},${p.y + o}H${mid - o}V${c.y + o}H${c.x}`
}
