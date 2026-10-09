import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import risk from '../fixtures/v2/risk_sample.json'
import results from '../fixtures/v2/results.json'
import rules from '../fixtures/v2/rules_sample.json'
import { LangProvider } from '../i18n'
import Home from './Home'

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))

function serve(overrides: Record<string, unknown> = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = new URL(String(input), 'http://x')
    if (url.pathname === '/api/v2/rules') return json(rules.rules)
    if (url.pathname === '/api/v2/results') return json(results)
    if (url.pathname === '/api/v2/risk') return json({ ...risk, rule: url.searchParams.get('rule'), ...overrides })
    return Promise.resolve(new Response('{}', { status: 404 }))
  })
}

const show = async () => {
  render(<LangProvider><Home /></LangProvider>)
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}

beforeEach(() => localStorage.clear())
afterEach(cleanup)

describe('Home', () => {
  it('level act renders the act wording, the first act time and the end of the act window', async () => {
    serve()
    await show()
    const headline = screen.getByRole('heading', { level: 2 })
    expect(headline.textContent).toContain('ACT')
    expect(headline.textContent).toContain(risk.first_act)
    const lastAct = risk.t[risk.p_unsafe.map((p, i) => (p >= 0.5 ? i : -1)).filter((i) => i >= 0).at(-1)!]
    expect(headline.textContent).toContain(lastAct)
    expect(headline.textContent).toContain('over-voltage')
  })

  it('a quiet day says so instead of naming a time', async () => {
    serve({ level: 'ok', first_watch: null, first_act: null, p_unsafe: Array(96).fill(0) })
    await show()
    expect(screen.getByRole('heading', { level: 2 }).textContent).toContain('OK')
  })

  it('the rule selector changes the request and shows the rule source and verification', async () => {
    const fetchMock = serve()
    await show()
    const riskCalls = () => fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/risk'))
    expect(riskCalls().at(-1)).toContain('rule=up_2005')
    fireEvent.click(screen.getByRole('button', { name: rules.rules[1].label }))
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
    expect(riskCalls().at(-1)).toContain('rule=pm10')
    expect(screen.getByText(new RegExp(rules.rules[1].source.replace(/[()]/g, '.')))).toBeTruthy()
    expect(screen.getByText(/secondary/)).toBeTruthy()
  })

  it('every number block carries a provenance tag', async () => {
    serve()
    await show()
    const blocks = document.querySelectorAll('[data-numbers]')
    expect(blocks.length).toBeGreaterThanOrEqual(3)
    blocks.forEach((b) => expect(b.querySelector('[data-provenance]'), b.getAttribute('data-numbers') ?? '').not.toBeNull())
  })

  it('chances that failed the held-out check say they are not reliable odds', async () => {
    serve()
    await show()
    expect(screen.getByRole('note').textContent).toMatch(/no better than the historical average/i)
  })

  it('chances that passed the held-out check are called slightly better than the historical average, never accurate', async () => {
    serve({ calibration: { reliable: true, raw: risk.p_unsafe, calibrated: risk.p_unsafe } })
    await show()
    const note = screen.getByRole('note').textContent ?? ''
    expect(note).toMatch(/slightly better than the historical average/i)
    expect(note).not.toMatch(/accurate/i)
  })

  it('a live forecast shows its anchor note with the inputs', async () => {
    serve({ provenance: { ...risk.provenance, anchor: 'pattern only: the UP anchor needs yesterday' } })
    await show()
    expect(screen.getByText(/pattern only: the UP anchor needs yesterday/)).toBeTruthy()
  })

  it('the demo-day selector lists the precomputed days and changes the requested date', async () => {
    const fetchMock = serve()
    await show()
    const riskCalls = () => fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/risk'))
    const days = screen.getByRole('group', { name: /day/i })
    expect(within(days).getAllByRole('button').length).toBe(3)
    // the day the API answered for is the one shown as selected
    expect(within(days).getByRole('button', { pressed: true }).textContent).toContain('Sunny')
    fireEvent.click(within(days).getByRole('button', { name: /cloudy/i }))
    await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
    expect(riskCalls().at(-1)).toContain('date=2025-08-05')
  })

  it('links to the printable evening report for the same day, rule and language', async () => {
    localStorage.setItem('gridtwin.lang', 'hi')
    serve()
    await show()
    const href = screen.getByRole('link', { name: /रिपोर्ट/ }).getAttribute('href')!
    const url = new URL(href, 'http://x')
    expect(url.pathname).toBe('/api/v2/report')
    expect(url.searchParams.get('rule')).toBe('up_2005')
    expect(url.searchParams.get('date')).toBe(risk.date)
    expect(url.searchParams.get('lang')).toBe('hi')
  })

  it('the strip has one bar per 15 minutes and the watch and act lines', async () => {
    serve()
    await show()
    const strip = screen.getByRole('img', { name: /probability/i })
    expect(strip.querySelectorAll('[data-step]').length).toBe(96)
    expect(strip.querySelectorAll('[data-threshold]').length).toBe(2)
  })
})
