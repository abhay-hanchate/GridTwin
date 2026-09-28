/** Plain-language wording shared by every screen: no engineering jargon on the surface. */

/** 15-minute steps -> "6 h 30 min". */
export function duration(steps: number): string {
  const minutes = steps * 15
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (!minutes) return '0 min'
  return [h ? `${h} h` : '', m ? `${m} min` : ''].filter(Boolean).join(' ')
}

export const SCENARIO_TEXT: Record<string, { short: string; long: string }> = {
  S1: { short: 'No solar', long: 'Today: no rooftop solar' },
  S2: { short: '3 in 10 homes', long: '3 in 10 homes have 3 kW rooftop solar' },
  S3: { short: '6 in 10 homes', long: '6 in 10 homes have 3 kW rooftop solar' },
  S4: { short: 'Every home', long: 'Every home has 3 kW rooftop solar' },
  S5: { short: 'Every home, strict rule', long: 'Every home has solar, judged by the stricter ±6% safety rule' },
}

export const ACTION_TEXT: Record<string, { name: string; how: string }> = {
  tap1_volt_var: {
    name: 'Turn the transformer down one notch + smart inverters',
    how: 'Both cheap settings together: the street gets 2.5% lower voltage and every inverter helps pull it down at noon.',
  },
  tap_plus2: {
    name: 'Turn the transformer down two notches',
    how: 'The whole street gets 5% lower voltage, set once for the season. Noon is fixed, but evenings drop too low.',
  },
  tap_plus1: {
    name: 'Turn the transformer down one notch',
    how: 'The whole street gets 2.5% lower voltage, set once for the season by the utility.',
  },
  volt_var: {
    name: 'Switch solar inverters to smart mode',
    how: 'Each home\'s inverter absorbs a little "reactive power", which pulls voltage down. No solar is wasted.',
  },
  export_cap_60: {
    name: 'Throw away 40% of the solar',
    how: 'Every panel is only allowed to send 60% of what it produces. This is what many utilities do today.',
  },
  export_cap_80: {
    name: 'Throw away 20% of the solar',
    how: 'Every panel is only allowed to send 80% of what it produces.',
  },
  battery_50kw: {
    name: 'Neighbourhood battery (50 kW)',
    how: 'A battery at the worst-affected spot on the wire charges whenever voltage gets high.',
  },
}

export const actionName = (id: string, fallback: string) => ACTION_TEXT[id]?.name ?? fallback

export const GLOSSARY: [string, string][] = [
  ['Voltage', 'The "pressure" of electricity. Indian homes are meant to get 230 V.'],
  ['Safe limit', '±10% of 230 V, so between 207 V and 253 V. Above that, appliances and solar inverters can fail.'],
  ['Transformer', 'The box on the pole that feeds the whole street. Its setting decides the starting voltage.'],
  ['Inverter', 'The device that turns a home\'s solar power into usable electricity. Modern ones can help control voltage.'],
  ['Digital twin', 'A computer copy of the street that we can test ideas on before touching the real one.'],
]

/** "2025-05-15" -> "15 May 2025". */
export function niceDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${d} ${months[m - 1]} ${y}`
}
