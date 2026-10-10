import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Fixes as FixesResult } from '../api/v2types'
import noSafeJson from '../fixtures/v2/fixes_no_safe_sample.json'
import safeJson from '../fixtures/v2/fixes_safe_sample.json'
import { LangProvider } from '../i18n'
import { calls, serve as serveBase, settle } from '../test/server'
import Fixes from './Fixes'

const noSafe = noSafeJson as unknown as FixesResult & { verdict: { binding_limit: NonNullable<FixesResult['verdict']['binding_limit']>; still_needs: string } }
const safe = safeJson as unknown as FixesResult

const serve = (fixes: unknown) => serveBase({ '/fixes': fixes })
const show = async (rule: string) => { render(<LangProvider><Fixes rule={rule} onRule={() => {}} /></LangProvider>); await settle() }
const tile = (id: string) => document.querySelector(`[data-fix="${id}"]`) as HTMLButtonElement

beforeEach(() => localStorage.clear())
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('Fixes, no safe action', () => {
  it('shows the no-safe-action panel with the binding limit, the closest option and what it still needs', async () => {
    serve(noSafe)
    await show('up_2005')
    const panel = screen.getByRole('region', { name: /no safe/i })
    expect(panel.textContent).toContain('over-voltage')
    expect(panel.textContent).toContain(String(Math.round(noSafe.verdict.binding_limit.worst.value * 230)))
    const closest = noSafe.outcomes.find((o) => o.id === noSafe.verdict.closest)!
    expect(panel.textContent).toContain(closest.label)
    expect(panel.textContent).toContain(noSafe.verdict.still_needs)
  })

  it('never shows a recommended badge', async () => {
    serve(noSafe)
    await show('up_2005')
    expect(document.querySelector('[data-recommended]')).toBeNull()
    // the label explainer at the end defines the word; nothing else on the page may use it
    const outside = [...document.querySelectorAll('.badge')].filter((b) => !b.closest('.explainer'))
    expect(outside.length).toBe(0)
  })

  it('opens the closest option, with its before and after voltage curves', async () => {
    serve(noSafe)
    await show('up_2005')
    expect(tile(noSafe.verdict.closest!).getAttribute('aria-pressed')).toBe('true')
    const chart = screen.getByRole('img', { name: /before and after/i })
    const series = chart.querySelectorAll('[data-series]')
    expect([...series].map((s) => s.getAttribute('data-series'))).toEqual(['before', 'after'])
    series.forEach((s) => expect(s.getAttribute('points')!.trim().split(' ').length).toBe(96))
  })
})

describe('Fixes, safe action found', () => {
  it('shows the recommended fix with unsafe quarter hours before and after', async () => {
    serve(safe)
    await show('pm10')
    const card = document.querySelector('[data-recommended]') as HTMLElement
    const winner = safe.outcomes.find((o) => o.id === safe.verdict.recommended)!
    expect(card.textContent).toContain(winner.label)
    expect(card.textContent).toContain(String(safe.verdict.baseline_unsafe_steps ?? safe.baseline_unsafe_steps))
    expect(screen.queryByRole('region', { name: /no safe/i })).toBeNull()
  })

  it('has one tile per fix tried, safe ones first', async () => {
    serve(safe)
    await show('pm10')
    const tiles = [...document.querySelectorAll('[data-fix]')]
    expect(tiles.length).toBe(safe.outcomes.length)
    const safeFlags = tiles.map((t) => safe.outcomes.find((o) => o.id === t.getAttribute('data-fix'))!.safe)
    expect(safeFlags).toEqual([...safeFlags].sort((a, b) => Number(b) - Number(a)))
  })

  it('clicking a fix explains it in plain words and plays it on the street with and without', async () => {
    const m = serve(safe)
    await show('pm10')
    const other = safe.outcomes.find((o) => o.id !== safe.verdict.recommended)!
    fireEvent.click(tile(other.id))
    await settle()
    const detail = screen.getByRole('region', { name: other.label })
    for (const q of [/what it is/i, /how it helps/i, /who does it/i, /what it costs/i]) expect(within(detail).getByText(q)).toBeTruthy()
    expect(calls(m, '/street').at(-1)).toContain(`fix=${other.id}`)
    const toggle = within(detail).getByRole('group', { name: /without or with/i })
    expect(within(toggle).getAllByRole('button').length).toBe(2)
    expect(within(detail).getAllByRole('img', { name: /the street at/i }).length).toBe(2)
    expect(within(detail).getByRole('img', { name: /before and after/i }).querySelector('.playhead-line')).toBeTruthy()
  })

  it('the phase list of the recommended fix shows each home with its from and to phase', async () => {
    serve(safe)
    await show('pm10')
    const table = screen.getByRole('table', { name: /phase moves/i })
    const rows = within(table).getAllByRole('row').slice(1)
    const moves = safe.outcomes[0].details!.phase_moves!
    expect(rows.length).toBe(moves.length)
    expect(rows[0].textContent).toContain(String(moves[0].home))
    expect(rows[0].textContent).toContain(moves[0].from)
    expect(rows[0].textContent).toContain(moves[0].to)
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
    serve({ ...safe, verdict: { ...safe.verdict, recommended: 'envelope' } })
    await show('pm10')
    const table = screen.getByRole('table', { name: /export limits/i })
    const limits = safe.outcomes[1].details!.export_limits!
    expect(within(table).getAllByRole('row').length).toBe(limits.homes.length + 1)
    expect(table.textContent).toContain(String(limits.kw[0][0]))
  })
})
