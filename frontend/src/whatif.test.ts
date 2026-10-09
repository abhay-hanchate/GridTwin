import { describe, expect, it } from 'vitest'
import catalog from './fixtures/v2/catalog.json'
import type { CatalogEntry } from './api/v2types'
import { choicesValid, chosen, initialChoices, paramProblem } from './whatif'

const entries = catalog as unknown as CatalogEntry[]

describe('paramProblem', () => {
  it('accepts values inside the bounds, including the bounds themselves', () => {
    expect(paramProblem({ type: 'number', minimum: 0, maximum: 10 }, '0')).toBeNull()
    expect(paramProblem({ type: 'number', minimum: 0, maximum: 10 }, '10')).toBeNull()
  })
  it('names the range when a value is outside it', () => {
    expect(paramProblem({ type: 'number', minimum: 0, maximum: 10 }, '25')).toEqual({ kind: 'range', min: 0, max: 10 })
  })
  it('treats exclusive bounds as exclusive', () => {
    expect(paramProblem({ type: 'number', exclusiveMinimum: 0, maximum: 500 }, '0')).toEqual({ kind: 'above', min: 0 })
    expect(paramProblem({ type: 'number', exclusiveMinimum: 0, maximum: 500 }, '0.1')).toBeNull()
  })
  it('rejects blanks, text and fractions for integers', () => {
    expect(paramProblem({ type: 'number' }, '')).toEqual({ kind: 'number' })
    expect(paramProblem({ type: 'number' }, 'abc')).toEqual({ kind: 'number' })
    expect(paramProblem({ type: 'integer', minimum: -2, maximum: 2 }, '1.5')).toEqual({ kind: 'integer' })
  })
})

describe('choices', () => {
  it('start with nothing chosen and every parameter at its default', () => {
    const c = initialChoices(entries)
    expect(Object.values(c).every((x) => !x.on)).toBe(true)
    expect(c['fix.battery'].values).toEqual({ kw: '50', hours: '4' })
  })
  it('only chosen entries count, and are sent with numbers', () => {
    const c = initialChoices(entries)
    c['change.panel_size'].values.kwp_per_home = '99'
    expect(choicesValid(entries, c)).toBe(true)                 // not chosen, so not checked
    c['change.panel_size'].on = true
    expect(choicesValid(entries, c)).toBe(false)
    c['change.panel_size'].values.kwp_per_home = '5'
    expect(chosen(entries, c, 'change')).toEqual([{ id: 'change.panel_size', params: { kwp_per_home: 5 } }])
    expect(chosen(entries, c, 'fix')).toEqual([])
  })
})
