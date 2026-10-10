import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ControlRecord, ControlRun, ControlRuns } from '../api/v2types'
import { LangProvider } from '../i18n'
import { serve, settle } from '../test/server'
import Control from './Control'

// Test input, not a result: two quarter hours, the second one unsafe after a fallback.
const check = (safe: boolean, vmax: number) => ({ safe, v_max_v: vmax, v_min_v: 230, line_max_pct: 40, trafo_pct: 30,
  vuf_pct: 0.5, margin_v: 253 - vmax, severity: safe ? 0 : vmax - 253, reasons: safe ? [] : ['over-voltage'] })
const rec = (step: number, time: string, safe: boolean): ControlRecord => ({
  step, time, energy_before_kwh: 30, energy_after_kwh: 31, soc_before: 0.5, soc_after: 0.52,
  action: { battery_kw: 4, keep: [1, 0.8, 1], topology_id: 'base', source: safe ? 'plan' : 'least_violation', curtailed_kwh: 1 },
  status: safe ? 'verified_safe' : 'unsafe_fallback', reason: safe ? 'planned action verified' : 'search exhausted',
  replan_triggers: ['every quarter hour'], topology_before: 'base', topology_after: 'base', operations_used: 0, operations_left: 2,
  planner: { status: 'verified_safe', rounds: [], predicted_infeasible_steps: [], horizon: 16, seconds: 1, switching_options: [] },
  before: check(false, 258), after: check(safe, safe ? 252 : 254),
  forecast: { forecast: {}, observed: {}, residual: {} }, plan_horizon: [],
})
const summary = { steps: 2, horizon: 16, statuses: { verified_safe: 1, unsafe_fallback: 1 }, unsafe_steps: 1,
  baseline_unsafe_steps: 2, unsafe_steps_without_control: 2, curtailed_kwh: 2, throughput_kwh: 2, baseline_throughput_kwh: 1,
  soc_min: 0.5, soc_max: 0.52, soc_final: 0.52, operations_used: 0, fallbacks: 1, replans: 2,
  infeasible_periods: [{ from: '12:15', until: '12:15', steps: 1, statuses: ['unsafe_fallback'], first_reason: 'search exhausted' }] }
const RUN: ControlRun = {
  config: { run_id: 'forecast_error', title: 'Forecast error', network_id: 'benchmark_250', rule_id: 'pm10', date: '2025-05-15',
    battery_kw: 30, battery_kwh: 60, soc_start: 0.5, soc_min: 0.1, soc_max: 0.9, curtail: true, switching: false, horizon: 16,
    max_operations: 2, perturbations: [] },
  provenance: { observations: 'simulated_observation' }, switches: [], records: [rec(48, '12:00', true), rec(49, '12:15', false)],
  baseline: { name: 'reactive', battery_kw: [0, 0], energy_kwh: [30, 30, 30], safe: [false, false], v_max_v: [258, 258],
    v_min_v: [230, 230], unsafe_steps: 2 },
  summary, timing: { total_s: 3, step_p50_s: 1.5, step_p95_s: 1.8, plan_p50_s: 1.4 }, limits_v: { min: 207, max: 253 },
}
const RUNS: ControlRuns = { runs: { forecast_error: { title: 'Forecast error', network_id: 'benchmark_250', rule_id: 'pm10', summary } },
  near_limit: { time: '09:15', limit_v: 253, rows: [{ solar_factor: 1, v_max_v: 252, safe: true, margin_v: 1 },
    { solar_factor: 1.1, v_max_v: 253.2, safe: false, margin_v: -0.2 }] } }

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('Control the day', () => {
  it('shows the comparison, the checked steps and the period it could not make safe', async () => {
    serve({ '/control/runs': RUNS, '/control/runs/forecast_error': RUN })
    render(<LangProvider><Control /></LangProvider>)
    await settle()
    expect(screen.getByText('1 of 2')).toBeTruthy()
    expect(document.querySelector('[data-numbers="control comparison"]')!.textContent).toMatch(/reactive battery rule on the same day: 2/)
    expect(document.querySelectorAll('[data-status="verified_safe"]').length).toBe(1)
    expect(document.querySelectorAll('[data-status="unsafe_fallback"]').length).toBe(1)
    expect(screen.getByRole('region', { name: /could not make safe/i }).textContent).toContain('12:15')
    expect(screen.getByRole('note').textContent).toMatch(/simulated/i)
    expect(screen.getByRole('region', { name: /close to the limit/i }).querySelectorAll('tr.unsafe').length).toBe(1)
  })

  it('runs a changed replay as a POST with the chosen settings', async () => {
    const m = serve({ '/control/runs': RUNS, '/control/runs/forecast_error': RUN, '/control/replay': RUN })
    render(<LangProvider><Control /></LangProvider>)
    await settle()
    fireEvent.click(screen.getByRole('checkbox', { name: /curtailment/i }))
    fireEvent.click(screen.getByRole('button', { name: /^run$/i }))
    await settle()
    const post = m.mock.calls.find((c) => String(c[0]).endsWith('/control/replay'))!
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ fixture: 'forecast_error', soc_start: 0.5, curtail: false, switching: false })
  })
})
