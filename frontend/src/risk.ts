import type { Level, LimitType, Risk } from './api/v2types'

export const levelOf = (p: number, watch: number, act: number): Level => (p >= act ? 'act' : p >= watch ? 'watch' : 'ok')

/** The limit most scenarios break (largest share); over-voltage when nothing is broken. */
export function dominantLimit(shares: Risk['shares']): LimitType {
  const entries = Object.entries(shares) as [LimitType, number][]
  return entries.reduce<[LimitType, number]>((best, e) => (e[1] > best[1] ? e : best), ['overvoltage', 0])[0]
}

export interface CauseSplit { grid: number[]; solar: number[]; solarShare: number | null }

/** Each step's chance of unsafe voltage split into what stays unsafe with every panel off (the grid's own voltage
 *  or demand) and what solar adds. `solarShare` is solar's part of all the unsafe chance in the day. Without the
 *  solar-off run (older results) nothing is attributed: everything counts as one part and the share is null. */
export function causeSplit(risk: Pick<Risk, 'p_unsafe' | 'p_unsafe_without_solar'>): CauseSplit {
  const dark = risk.p_unsafe_without_solar
  if (!dark || dark.length !== risk.p_unsafe.length) {
    return { grid: risk.p_unsafe.map(() => 0), solar: [...risk.p_unsafe], solarShare: null }
  }
  const grid = risk.p_unsafe.map((p, i) => Math.min(p, dark[i]))
  const solar = risk.p_unsafe.map((p, i) => p - grid[i])
  const total = risk.p_unsafe.reduce((a, b) => a + b, 0)
  return { grid, solar, solarShare: total > 0 ? solar.reduce((a, b) => a + b, 0) / total : null }
}
