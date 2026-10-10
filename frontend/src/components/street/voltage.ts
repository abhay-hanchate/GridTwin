const NEAR_V = 2.5                               // within this many volts of a limit counts as "close"

/** The colour class of a home's voltage against the rule's limits. */
export function homeClass(v: number | null, lim: { min: number; max: number }): string {
  if (v === null || !Number.isFinite(v)) return 'v-none'           // the power flow had no solution here
  if (v > lim.max) return 'v-over'
  if (v < lim.min) return 'v-under'
  if (v > lim.max - NEAR_V || v < lim.min + NEAR_V) return 'v-near'
  return 'v-ok'
}
