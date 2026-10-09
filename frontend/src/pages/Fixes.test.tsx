import { act, cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Fixes as FixesResult } from '../api/v2types'
import noSafeJson from '../fixtures/v2/fixes_no_safe_sample.json'
import safeJson from '../fixtures/v2/fixes_safe_sample.json'
import rules from '../fixtures/v2/rules_sample.json'
import { LangProvider } from '../i18n'
import Fixes from './Fixes'

const noSafe = noSafeJson as unknown as FixesResult & { verdict: { binding_limit: NonNullable<FixesResult['verdict']['binding_limit']>; still_needs: string } }
const safe = safeJson as unknown as FixesResult

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))

function serve(fixes: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = new URL(String(input), 'http://x')
    if (url.pathname === '/api/v2/rules') return json(rules.rules)
    if (url.pathname === '/api/v2/fixes') return json(fixes)
    return Promise.resolve(new Response('{}', { status: 404 }))
  })
}

const show = async (rule: string) => {
  render(<LangProvider><Fixes rule={rule} onRule={() => {}} /></LangProvider>)
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}

beforeEach(() => localStorage.clear())
afterEach(cleanup)

describe('Fixes, no safe action', () => {
  it('shows the no-safe-action panel with the binding limit, the closest option and what it still needs', async () => {
    serve(noSafe)
    await show('up_2005')
    const panel = screen.getByRole('region', { name: /no safe action/i })
    expect(panel.textContent).toContain('over-voltage')
    expect(panel.textContent).toContain(String(Math.round(noSafe.verdict.binding_limit.worst.value * 230)))
    const closest = noSafe.outcomes.find((o) => o.id === noSafe.verdict.closest)!
    expect(panel.textContent).toContain(closest.label)
    expect(panel.textContent).toContain(noSafe.verdict.still_needs)
  })

  it('never shows a recommended badge', async () => {
    serve(noSafe)
    await show('up_2005')
    expect(screen.queryByText(/^recommended$/i)).toBeNull()
    expect(document.querySelector('[data-recommended]')).toBeNull()
  })

  it('the before/after chart for the closest option receives both series', async () => {
    serve(noSafe)
    await show('up_2005')
    const chart = screen.getByRole('img', { name: /before and after/i })
    const series = chart.querySelectorAll('[data-series]')
    expect([...series].map((s) => s.getAttribute('data-series'))).toEqual(['before', 'after'])
    series.forEach((s) => expect(s.getAttribute('points')!.trim().split(' ').length).toBe(96))
  })
})

describe('Fixes, safe action found', () => {
  it('shows the recommended card with its cost lines', async () => {
    serve(safe)
    await show('pm10')
    const card = document.querySelector('[data-recommended]') as HTMLElement
    expect(card).not.toBeNull()
    const winner = safe.outcomes[0]
    expect(card.textContent).toContain(winner.label)
    expect(within(card).getByText(/held back/i).textContent).toContain(String(winner.cost.curtailed_kwh))
    expect(within(card).getByText(/operations/i).textContent).toContain(String(winner.cost.operations))
    expect(within(card).getByText(/margin/i).textContent).toContain(String(winner.cost.margin_v))
    expect(screen.queryByRole('region', { name: /no safe action/i })).toBeNull()
  })

  it('the phase list shows each home with its from and to phase', async () => {
    serve(safe)
    await show('pm10')
    const table = screen.getByRole('table', { name: /phase moves/i })
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.length).toBe(safe.outcomes[0].details!.phase_moves!.length)
    const first = safe.outcomes[0].details!.phase_moves![0]
    expect(rows[0].textContent).toContain(String(first.home))
    expect(rows[0].textContent).toContain(first.from)
    expect(rows[0].textContent).toContain(first.to)
  })

  it('the compare table lists every option tried', async () => {
    serve(safe)
    await show('pm10')
    const table = screen.getByRole('table', { name: /every option/i })
    expect(within(table).getAllByRole('row').length).toBe(safe.outcomes.length + 1)
  })
})

describe('Envelope table', () => {
  it('shows a limit for each home and step', async () => {
    const env = { ...safe, verdict: { ...safe.verdict, recommended: 'envelope' } }
    serve(env)
    await show('pm10')
    const table = screen.getByRole('table', { name: /export limits/i })
    const limits = safe.outcomes[1].details!.export_limits!
    expect(within(table).getAllByRole('row').length).toBe(limits.homes.length + 1)
    expect(table.textContent).toContain(String(limits.kw[0][0]))
  })
})
