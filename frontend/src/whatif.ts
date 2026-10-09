import type { CatalogEntry, ParamSchema } from './api/v2types'

/** Why `raw` is not an acceptable value for `schema`, or null if it is. The API checks again (422). */
export type ParamProblem =
  | { kind: 'number' }
  | { kind: 'integer' }
  | { kind: 'range'; min: number; max: number }
  | { kind: 'above'; min: number }
  | { kind: 'below'; max: number }

export function paramProblem(schema: ParamSchema, raw: string): ParamProblem | null {
  const x = raw.trim() === '' ? NaN : Number(raw)
  if (!Number.isFinite(x)) return { kind: 'number' }
  if (schema.type === 'integer' && !Number.isInteger(x)) return { kind: 'integer' }
  const { minimum: lo, maximum: hi, exclusiveMinimum: xlo, exclusiveMaximum: xhi } = schema
  if ((lo !== undefined && x < lo) || (hi !== undefined && x > hi)) {
    if (lo !== undefined && hi !== undefined) return { kind: 'range', min: lo, max: hi }
    return lo !== undefined ? { kind: 'above', min: lo } : { kind: 'below', max: hi! }
  }
  if (xlo !== undefined && x <= xlo) return { kind: 'above', min: xlo }
  if (xhi !== undefined && x >= xhi) return { kind: 'below', max: xhi }
  return null
}

export type Choice = { on: boolean; values: Record<string, string> }

/** The form's starting state: nothing chosen, every parameter at its schema default. */
export function initialChoices(catalog: CatalogEntry[]): Record<string, Choice> {
  return Object.fromEntries(catalog.map((e) => [e.id, {
    on: false,
    values: Object.fromEntries(Object.entries(e.params.properties ?? {}).map(([k, p]) => [k, p.default === undefined ? '' : String(p.default)])),
  }]))
}

/** True when every chosen entry has acceptable values. */
export function choicesValid(catalog: CatalogEntry[], choices: Record<string, Choice>): boolean {
  return catalog.every((e) => !choices[e.id]?.on || Object.entries(e.params.properties ?? {})
    .every(([k, p]) => paramProblem(p, choices[e.id].values[k] ?? '') === null))
}

/** The chosen entries of one kind as the API expects them: [{id, params}] with numbers. */
export function chosen(catalog: CatalogEntry[], choices: Record<string, Choice>, kind: string) {
  return catalog.filter((e) => e.kind === kind && choices[e.id]?.on).map((e) => ({
    id: e.id,
    params: Object.fromEntries(Object.keys(e.params.properties ?? {}).map((k) => [k, Number(choices[e.id].values[k])])),
  }))
}
