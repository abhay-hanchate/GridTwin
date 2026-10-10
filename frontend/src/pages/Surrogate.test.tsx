import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AREAS } from '../app/areas'
import rules from '../fixtures/v2/rules_sample.json'
import { LangProvider } from '../i18n'
import { serve, settle } from '../test/server'
import Surrogate, { type SurrogatePayload, type SurrogateStreet } from './Surrogate'

// Test input in the GET /surrogate shape, not a result.
const scr = (fs: number, unsafe: number, fr: number, safe: number) => ({ unsafe_as_safe: fs, truly_unsafe: unsafe, false_rejections: fr, truly_safe: safe })
const street = (id: string, selected: string, e2 = true): SurrogateStreet => ({
  id, selected, selection_reason: 'lowest', states: { train: 44958, test: 22447, boundary_test: 4015, out_of_range: 2000, test_supported: 11201 },
  guard_v: [0.87, 0.65], guard_loading_pts: [1.25, 0.75], shipped_round: 3,
  rounds: [{ round: 1, rule: 'pm10', unsafe_as_safe: 0, truly_unsafe: 1500, false_rejections: 9100, truly_safe: 14900 },
    { round: 2, rule: 'pm10', unsafe_as_safe: 2, truly_unsafe: 1500, false_rejections: 840, truly_safe: 14900 },
    { round: 3, rule: 'pm10', unsafe_as_safe: 1, truly_unsafe: 1400, false_rejections: 6200, truly_safe: 15100 }],
  support: { taps: [0, 1, 2], modes: ['fixed_pf', 'volt_var'], battery_node: 65, battery_kw: [-99.9, 99.8], upstream_pu: [0.85, 1.2] },
  candidates: [
    { kind: 'ridge', selected: selected === 'ridge', node_level: true, voltage_mae_v: 0.71, voltage_p99_v: 3.4, loading_mae_pts: 0.52,
      loading_p99_pts: 2.6, boundary_voltage_p99_v: 3.9, gates_passed: 2, gates_total: 4 },
    { kind: 'lgbm', selected: selected === 'lgbm', node_level: false, voltage_mae_v: 0.44, voltage_p99_v: 2.2, loading_mae_pts: 0.33,
      loading_p99_pts: 1.8, boundary_voltage_p99_v: 2.7, gates_passed: 3, gates_total: 4 },
    { kind: 'mlp', selected: selected === 'mlp', node_level: true, voltage_mae_v: 0.31, voltage_p99_v: 1.6, loading_mae_pts: 0.21,
      loading_p99_pts: 1.1, boundary_voltage_p99_v: 2.1, gates_passed: 4, gates_total: 4 },
  ],
  gates: [{ name: 'voltage_mae_v', value: 0.31, target: 0.5, passed: true }, { name: 'voltage_p99_v', value: 2.6, target: 2, passed: false }],
  screening: [{ rule: 'pm10', split: 'boundary', guarded: scr(3, 1800, 120, 2215), point: scr(41, 1800, 60, 2215) }],
  out_of_range: [{ kind: 'tap_negative', states: 250, unsupported: 250 }, { kind: 'layout', states: 250, unsupported: 250 }],
  latency: [{ mode: 'volt_var', batch: 1024, screen_ms_per_state: 0.0123, solver_ms_per_state: 31.7 }],
  e1: { runs: 32, speedup_vs_solve_all: 5.12, speedup_vs_cost_order: 1.37, same_choice_as_solve_all: 30, false_rejections: 7, overrules: 1 },
  e2: e2 ? { runs: 8, speedup: 0.97, skipped_candidates: 22, candidates: 198, false_rejections: 0, same_best: 8 } : null,
})
const PAYLOAD: SurrogatePayload = {
  provenance: 'simulated', generated_at: '2026-10-10T18:00:00+00:00',
  screener: { active: false, streets: [], reason: 'no usable artifact' },
  streets: [street('benchmark_250', 'mlp'), street('rural_weak_63', 'ridge', false)],
  disagreements: { counts: [{ source: 'held-out test split', type: 'point prediction said safe', rows: 41 }],
    examples: [{ source: 'held-out test split', type: 'point prediction said safe', caught_by_guard: true,
      predicted: { v_max_v: 252.6 }, guarded: { v_max_v: 253.5 }, solver: { v_max_v: 253.4 } }] },
}

const show = async () => { render(<LangProvider><Surrogate /></LangProvider>); await settle() }

beforeEach(() => localStorage.clear())
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('Surrogate', () => {
  it('shows the three models, marks the chosen one and keeps a missed target visible', async () => {
    serve({ '/surrogate': PAYLOAD })
    await show()
    const table = screen.getByRole('table', { name: /how close/i })
    expect(table.querySelectorAll('tbody tr').length).toBe(3)
    expect(table.querySelector('tr[data-selected="true"]')?.textContent).toContain('Neural network')
    expect(document.querySelector('[data-gate="voltage_p99_v"]')?.textContent).toContain('Not met')
    expect(document.querySelector('[data-gate="voltage_mae_v"]')?.textContent).toContain('Met')
  })

  it('says when the screen is off and why, and labels the states as simulated', async () => {
    serve({ '/surrogate': PAYLOAD })
    await show()
    expect(document.querySelector('[data-active="false"]')?.textContent).toContain('no usable artifact')
    expect(screen.getAllByText(/simulated/i).length).toBeGreaterThan(0)
  })

  it('shows every out-of-range input going to the solver and the misses with their denominators', async () => {
    serve({ '/surrogate': PAYLOAD })
    await show()
    const limits = screen.getByRole('table', { name: /know its limits/i })
    expect(limits.querySelectorAll('tr[data-all-refused="true"]').length).toBe(2)
    expect(limits.textContent).toContain('250 of 250')
    expect(screen.getByRole('table', { name: /unsafe states through/i }).textContent).toContain('3 of 1800')
  })

  it('a run that did not happen says so instead of showing a number', async () => {
    serve({ '/surrogate': PAYLOAD })
    await show()
    fireEvent.click(screen.getByRole('button', { name: 'Rural weak feeder' }))
    expect(document.querySelector('[data-section="e2"]')?.textContent).toBe('Not run yet.')
    expect(document.querySelector('[data-section="e1"]')?.textContent).toContain('5.12')
  })

  it('every number on the page exists in the response (honesty rule)', async () => {
    serve({ '/surrogate': PAYLOAD })
    await show()
    const numbers = (text: string) => text.match(/\d+(?:\.\d+)?/g) ?? []
    // The page reads /surrogate and the rule labels from /rules; the kicker shows the tab's position.
    const allowed = new Set([...numbers(JSON.stringify(PAYLOAD)), ...numbers(JSON.stringify(rules)), String(AREAS.indexOf('surrogate'))])
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    const shown = new Set<string>()
    for (let n = walker.nextNode(); n; n = walker.nextNode()) numbers(n.textContent ?? '').forEach((x) => shown.add(x))
    expect(shown.size).toBeGreaterThan(10)
    for (const n of shown) expect(allowed.has(n), `"${n}" is on the page but not in the response`).toBe(true)
  })

  it('compares one margin for every state with margins by predicted value, and marks the one in use', async () => {
    serve({ '/surrogate': PAYLOAD })
    await show()
    const rounds = screen.getByRole('table', { name: /round by round/i })
    expect(rounds.querySelectorAll('tbody tr').length).toBe(3)
    expect(rounds.querySelectorAll('tr[data-in-use="true"]').length).toBe(1)
    expect(rounds.querySelector('tr[data-in-use="true"]')?.textContent).toContain('6200 of 15100')
    expect(rounds.textContent).toContain('fresh test set')
    expect(screen.getByRole('region', { name: /chosen model/i }).textContent).toContain('11201')
  })

  it('a missing evaluation is an error, not an empty page', async () => {
    serve({ '/surrogate': { error: { code: 'unavailable', message: 'the surrogate evaluation is missing', details: {} } } },
      { status: { '/surrogate': 503 } })
    await show()
    expect(screen.getByRole('alert').textContent).toContain('the surrogate evaluation is missing')
  })
})
