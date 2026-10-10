import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import risk from '../fixtures/v2/risk_sample.json'
import rules from '../fixtures/v2/rules_sample.json'
import { LangProvider } from '../i18n'
import { CALENDAR, calls, serve as serveBase, settle } from '../test/server'
import Forecast from './Forecast'

const verdictHeading = () => document.querySelector('h2.verdict') as HTMLElement
const serve = (overrides: Record<string, unknown> = {}) =>
  serveBase({ '/risk': (url: URL) => ({ ...risk, rule: url.searchParams.get('rule'), date: url.searchParams.get('date'), ...overrides }) })
const show = async () => { render(<LangProvider><Forecast /></LangProvider>); await settle() }

beforeEach(() => localStorage.clear())
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('Tomorrow', () => {
  it('asks for the real tomorrow by default and names the day in the headline', async () => {
    const m = serve()
    await show()
    expect(calls(m, '/risk').at(-1)).toContain(`date=${CALENDAR.tomorrow}`)
    expect(verdictHeading().textContent).toMatch(/^ACT\s*Tomorrow:/)
  })

  it('level act renders the act wording, the first act time and the end of the act window', async () => {
    serve()
    await show()
    const headline = verdictHeading()
    expect(headline.textContent).toContain(risk.first_act)
    const lastAct = risk.t[risk.p_unsafe.map((p, i) => (p >= 0.5 ? i : -1)).filter((i) => i >= 0).at(-1)!]
    expect(headline.textContent).toContain(lastAct)
    expect(headline.textContent).toContain('over-voltage')
  })

  it('a past day is named by its date, never as tomorrow', async () => {
    serve()
    await show()
    fireEvent.change(screen.getByLabelText(/pick a date/i), { target: { value: '2025-11-19' } })
    await settle()
    expect(verdictHeading().textContent).toContain('19 November 2025')
    expect(verdictHeading().textContent).not.toMatch(/tomorrow/i)
  })

  it('a quiet day says so instead of naming a time', async () => {
    serve({ level: 'ok', first_watch: null, first_act: null, p_unsafe: Array(96).fill(0) })
    await show()
    expect(verdictHeading().textContent).toContain('OK')
    expect(verdictHeading().textContent).toMatch(/no unsafe period/i)
  })

  it('says the grid is the cause when the street stays unsafe with every panel off', async () => {
    serve({ p_unsafe_without_solar: risk.p_unsafe })
    await show()
    expect(document.querySelector('.verdict-box .cause')!.textContent).toMatch(/grid's own voltage/i)
  })

  it('says solar is the cause when switching the panels off removes the risk', async () => {
    serve({ p_unsafe_without_solar: risk.p_unsafe.map(() => 0) })
    await show()
    expect(document.querySelector('.verdict-box .cause')!.textContent).toMatch(/rooftop solar/i)
  })

  it('the rule selector changes the request and shows the rule source and verification', async () => {
    const m = serve()
    await show()
    expect(calls(m, '/risk').at(-1)).toContain('rule=up_2005')
    fireEvent.click(screen.getByRole('button', { name: rules.rules[1].label }))
    await settle()
    expect(calls(m, '/risk').at(-1)).toContain('rule=pm10')
    expect(screen.getByText(new RegExp(rules.rules[1].source.replace(/[()]/g, '.')))).toBeTruthy()
  })

  it('every number block carries a provenance tag', async () => {
    serve()
    await show()
    const blocks = document.querySelectorAll('[data-numbers]')
    expect(blocks.length).toBeGreaterThanOrEqual(3)
    blocks.forEach((b) => expect(b.querySelector('[data-provenance]') ?? b.closest('section')?.querySelector('[data-provenance]'),
      b.getAttribute('data-numbers') ?? '').not.toBeNull())
  })

  it('chances that failed the held-out check say they are not reliable odds', async () => {
    serve()
    await show()
    expect(screen.getByRole('note').textContent).toMatch(/no better than the historical average/i)
  })

  it('chances that passed the held-out check are called slightly better than the historical average, never accurate', async () => {
    serve({ series: 'calibrated', calibration: { reliable: true, applied: true, raw: risk.p_unsafe, calibrated: risk.p_unsafe } })
    await show()
    const note = screen.getByRole('note').textContent ?? ''
    expect(note).toMatch(/slightly better than the historical average/i)
    expect(note).not.toMatch(/accurate/i)
  })

  it('a reliable map that does not apply here (a fix or another street) says the chances are raw', async () => {
    serve({ series: 'raw', calibration: { reliable: true, applied: false, raw: risk.p_unsafe, calibrated: risk.p_unsafe } })
    await show()
    expect(screen.getByRole('note').textContent).toMatch(/raw chances/i)
  })

  it('calibrated chances drive the chart and the hours, and drop the raw scenario range', async () => {
    const p = risk.p_unsafe.map((x) => Math.min(1, x + 0.1))
    serve({ series: 'calibrated', p_unsafe: p, expected_unsafe_hours: { mean: 7.5, p10: null, p90: null },
      calibration: { reliable: true, applied: true, raw: risk.p_unsafe, calibrated: p } })
    await show()
    const strip = screen.getByRole('img', { name: /probability/i })
    expect(strip.querySelectorAll('[data-step]').length).toBe(p.length)
    const kpi = document.querySelector('[data-numbers="expected unsafe hours"]')!.textContent ?? ''
    expect(kpi).toContain('7.5')
    expect(kpi).not.toMatch(/P10/)
  })

  it('links to the printable evening report for the same day, rule and language', async () => {
    localStorage.setItem('gridtwin.lang', 'hi')
    serve()
    await show()
    const url = new URL(screen.getByRole('link', { name: /रिपोर्ट/ }).getAttribute('href')!, 'http://x')
    expect(url.pathname).toBe('/api/v2/report')
    expect(url.searchParams.get('rule')).toBe('up_2005')
    expect(url.searchParams.get('date')).toBe(CALENDAR.tomorrow)
    expect(url.searchParams.get('lang')).toBe('hi')
  })

  it('the strip has one bar per 15 minutes and the watch and act lines', async () => {
    serve()
    await show()
    const strip = screen.getByRole('img', { name: /probability/i })
    expect(strip.querySelectorAll('[data-step]').length).toBe(96)
    expect(strip.querySelectorAll('[data-threshold]').length).toBe(2)
  })

  it('offline, only the computed days are offered', async () => {
    serveBase({ '/risk': risk }, { offline: true })
    await show()
    const days = screen.getByRole('group', { name: /^day$/i })
    expect(within(days).getAllByRole('button').map((b) => b.textContent)).toEqual(CALENDAR.ready)
    expect(within(days).getByRole('button', { pressed: true }).textContent).toBe(CALENDAR.ready.at(-1))
  })

  it('ends by explaining every level and pointing to the fixes', async () => {
    serve()
    render(<LangProvider><Forecast go={vi.fn()} /></LangProvider>)
    await settle()
    const explainer = screen.getByRole('region', { name: /what the labels mean/i })
    for (const level of ['OK', 'WATCH', 'ACT']) expect(within(explainer).getByText(level)).toBeTruthy()
    expect(screen.getByRole('button', { name: /^fixes/i })).toBeTruthy()
  })

  it('says why past days of one month look alike, but not for the real tomorrow', async () => {
    serve()
    await show()
    expect(screen.queryByText(/days of the same month look alike/i)).toBeNull()
    fireEvent.change(screen.getByLabelText(/pick a date/i), { target: { value: '2025-12-18' } })
    await settle()
    expect(screen.getByText(/days of the same month look alike/i)).toBeTruthy()
  })
})
