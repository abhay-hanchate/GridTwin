import { PHASES } from './balance'

/** Where everything on the street map sits. Wide screens: transformer on the left, the three phases running right.
 *  Phones: transformer on top, the phases running down in three columns. Houses always stand upright. */

export type Phase = (typeof PHASES)[number]

export interface Slot {
  h: number
  x: number                       // house centre
  top: number                     // roof ridge
  tap: { x: number; y: number }   // where its drop meets the phase wire
  drop: string                    // the drop, from the phase wire to the house
  tipAbove: boolean
}

export interface Geo {
  W: number
  H: number
  tx: number
  ty: number
  pole: { top: number; bottom: number }
  plate: { x: number; y: number }        // the kVA plate's centre
  load: { x: number; y: number }
  grid: { path: string; label: { x: number; y: number } }
  feeder: Record<Phase, string>
  lane: Record<Phase, { x: number; y: number; w: number; h: number }>
  label: Record<Phase, { cx: number; cy: number; tx: number; ty: number; anchor: 'start' | 'end' }>
  arrow: { back: string; draw: string }
  slots: Slot[]
}

/** The homes of each phase, nearest the transformer first. */
function byPhase(phase: Phase[], dist: number[]): Record<Phase, number[]> {
  const out = { A: [], B: [], C: [] } as Record<Phase, number[]>
  phase.forEach((p, i) => out[p].push(i))
  for (const p of PHASES) out[p].sort((a, b) => dist[a] - dist[b] || a - b)
  return out
}

export function landscape(phase: Phase[], dist: number[]): Geo {
  const W = 1200, H = 590, TX = 96, X0 = 300, X1 = 1172
  const Y: Record<Phase, number> = { A: 112, B: 292, C: 472 }
  const TY = Y.B
  const slots: Slot[] = []
  const groups = byPhase(phase, dist)
  for (const p of PHASES) {
    const ids = groups[p]
    const gap = Math.min(96, (X1 - X0 - 30) / Math.max(1, Math.ceil(ids.length / 2)))
    ids.forEach((h, j) => {
      const up = j % 2 === 0                       // alternate above and below the wire
      const x = X0 + 14 + Math.floor(j / 2) * gap + (up ? 0 : gap / 2)
      const y = Y[p]
      const top = up ? y - 58 : y + 22
      slots[h] = { h, x, top, tap: { x, y }, drop: `M${x},${y} V${up ? y - 22 : y + 22}`, tipAbove: up }
    })
  }
  const rec = <T,>(f: (p: Phase) => T) => Object.fromEntries(PHASES.map((p) => [p, f(p)])) as Record<Phase, T>
  return {
    W, H, tx: TX, ty: TY, pole: { top: TY - 120, bottom: TY + 36 },
    plate: { x: TX, y: TY + 56 }, load: { x: TX, y: TY + 86 },
    grid: { path: `M4,${TY - 120} H${TX} V${TY - 44}`, label: { x: 10, y: TY - 130 } },
    feeder: rec((p) => `M${TX + 34},${TY} C${TX + 130},${TY} ${X0 - 150},${Y[p]} ${X0 - 60},${Y[p]} H${X1 + 14}`),
    lane: rec((p) => ({ x: X0 - 70, y: Y[p] - 72, w: X1 - X0 + 94, h: 144 })),
    label: rec((p) => {
      const dy = p === 'C' ? 30 : -30                // C's feeder arrives from above, so its label sits below
      return { cx: X0 - 94, cy: Y[p] + dy, tx: X0 - 76, ty: Y[p] + dy + 5, anchor: 'start' as const }
    }),
    arrow: { back: '←', draw: '→' },
    slots,
  }
}

export function portrait(phase: Phase[], dist: number[]): Geo {
  const W = 660, TX = 330, TY = 112, Y0 = 300
  const X: Record<Phase, number> = { A: 110, B: 330, C: 550 }
  const groups = byPhase(phase, dist)
  const rows = Math.max(1, ...PHASES.map((p) => Math.ceil(groups[p].length / 2)))
  const gap = Math.min(96, Math.max(50, 920 / rows))
  const H = Y0 + rows * gap + 40
  const slots: Slot[] = []
  for (const p of PHASES) {
    groups[p].forEach((h, j) => {
      const left = j % 2 === 0                     // alternate left and right of the wire
      const y = Y0 + Math.floor(j / 2) * gap + (left ? 0 : gap / 2)
      const x = X[p] + (left ? -50 : 50)
      slots[h] = { h, x, top: y - 22, tap: { x: X[p], y }, drop: `M${X[p]},${y} H${x + (left ? 13 : -13)}`, tipAbove: true }
    })
  }
  const rec = <T,>(f: (p: Phase) => T) => Object.fromEntries(PHASES.map((p) => [p, f(p)])) as Record<Phase, T>
  return {
    W, H, tx: TX, ty: TY, pole: { top: TY - 96, bottom: TY + 40 },
    plate: { x: TX + 90, y: TY - 8 }, load: { x: TX + 90, y: TY + 22 },
    grid: { path: `M4,${TY - 86} H${TX} V${TY - 44}`, label: { x: 10, y: TY - 96 } },
    feeder: rec((p) => `M${TX},${TY + 40} C${TX},${TY + 120} ${X[p]},${TY + 100} ${X[p]},${Y0 - 70} V${H - 14}`),
    lane: rec((p) => ({ x: X[p] - 100, y: Y0 - 54, w: 200, h: H - Y0 + 40 })),
    label: rec((p) => ({ cx: X[p] - 24, cy: Y0 - 56, tx: X[p] + 8, ty: Y0 - 50, anchor: 'start' as const })),
    arrow: { back: '↑', draw: '↓' },
    slots,
  }
}
