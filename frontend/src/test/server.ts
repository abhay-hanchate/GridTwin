import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act } from '@testing-library/react'
import { vi } from 'vitest'
import type { Calendar, Results, Street, StreetRun } from '../api/v2types'
import rules from '../fixtures/v2/rules_sample.json'

// The file GET /results serves (written by python -m scripts.evaluate), read directly so tests never check a copy.
export const results: Results = JSON.parse(readFileSync(resolve(import.meta.dirname, '../../../data/results/results.json'), 'utf-8'))

export const CALENDAR: Calendar = {
  tomorrow: '2026-10-11', archive: { first: '2025-01-01', last: '2025-12-31' },
  ready: ['2025-05-15', '2025-08-05', '2025-11-19'], offline: false,
}

const STEPS = 96
const T = Array.from({ length: STEPS }, (_, i) => `${String(Math.floor(i / 4)).padStart(2, '0')}:${String((i % 4) * 15).padStart(2, '0')}`)

/** A tiny street in the /street shape: transformer, three nodes in a row, two homes on phases A and B. Midday (steps
 *  40 to 56) exports solar and pushes home 1 over the limit; with a fix it stays inside. Test input, not a result. */
export function makeStreet(fix = 'none'): Street {
  const run = (cap: number): StreetRun => ({
    home_v: T.map((_, i) => [i >= 40 && i < 56 ? cap : 236, 234]),
    home_phase: ['A', 'B'],
    line_phase_kw: T.map((_, i) => (i >= 40 && i < 56 ? [[-3, 0.5, 0], [-3, 0, 0]] : [[0.4, 0.5, 0], [0.4, 0, 0]])),
    line_neutral_a: T.map(() => [2, 1]),
    line_loading_pct: T.map(() => [20, 10]),
    trafo_kw: T.map((_, i) => (i >= 40 && i < 56 ? -2.5 : 0.9)),
    trafo_loading_pct: T.map(() => 4),
    solar_kw: T.map((_, i) => (i >= 40 && i < 56 ? 3 : 0)),
    neutral_a: T.map(() => 2),
    unsafe: T.map((_, i) => cap > 253 && i >= 40 && i < 56),
    summary: { max_vm_pu: cap / 230, min_vm_pu: 1.01, violation_steps: cap > 253 ? 16 : 0, solver_failed_steps: 0,
      max_trafo_loading_pct: 4, max_line_loading_pct: 20, curtailed_kwh: 0 },
  })
  return {
    date: '2026-10-11', network: 'benchmark_250', rule: 'pm10', fix, t: T, limits_v: { min: 207, max: 253 },
    layout: { root: 0, rows: 1, nodes: [0, 1, 2].map((id) => ({ id, x: id, y: 0 })),
      lines: [{ line: 0, from: 0, to: 1 }, { line: 1, from: 1, to: 2 }] },
    homes: [{ node: 1, kwp: 3 }, { node: 2, kwp: 0 }], trafo_kva: 250,
    before: run(258), ...(fix === 'none' ? {} : { after: run(249), fix_label: 'Test fix' }),
    flow_method: 'estimated', provenance: { solar: 'modeled' },
  }
}

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }))
type Handler = unknown | ((url: URL, init?: RequestInit) => unknown)

/** Mock fetch for /api/v2: the shared routes answer by default, `routes` add or override (by path after /api/v2). */
export function serve(routes: Record<string, Handler> = {}, { offline = false, status = {} as Record<string, number> } = {}) {
  const all: Record<string, Handler> = {
    '/rules': rules.rules, '/results': results, '/calendar': { ...CALENDAR, offline },
    '/readiness': { ready: true, mode: offline ? 'offline' : 'online', checks: {} },
    '/street': (url: URL) => makeStreet(url.searchParams.get('fix') ?? 'none'),
    ...routes,
  }
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = new URL(String(input), 'http://x')
    const path = url.pathname.replace('/api/v2', '')
    if (!(path in all)) return json({ error: { message: 'not served in this test' } }, 503)
    const h = all[path]
    return json(typeof h === 'function' ? (h as (u: URL, i?: RequestInit) => unknown)(url, init) : h, status[path] ?? 200)
  })
}

export const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 0)) })
export const calls = (m: ReturnType<typeof serve>, path: string) =>
  m.mock.calls.map((c) => String(c[0])).filter((u) => new URL(u, 'http://x').pathname === `/api/v2${path}`)
