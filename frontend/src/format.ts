/** Number formatting shared by the v2 pages. Values always come from an API response. */
export const pct = (p: number) => `${Math.round(p * 100)}%`
export const one = (x: number) => String(Number(x.toFixed(1)))
export const volts = (v: number) => String(Math.round(v))
/** HH:MM of step `i` in a 96-step day of 15-minute steps (used when a response has no `t`). */
export const stepTime = (i: number) => `${String(Math.floor(i / 4)).padStart(2, '0')}:${String((i % 4) * 15).padStart(2, '0')}`
