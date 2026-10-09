import type { Level, LimitType, Risk } from './api/v2types'

export const levelOf = (p: number, watch: number, act: number): Level => (p >= act ? 'act' : p >= watch ? 'watch' : 'ok')

/** The limit most scenarios break (largest share); over-voltage when nothing is broken. */
export function dominantLimit(shares: Risk['shares']): LimitType {
  const entries = Object.entries(shares) as [LimitType, number][]
  return entries.reduce<[LimitType, number]>((best, e) => (e[1] > best[1] ? e : best), ['overvoltage', 0])[0]
}
