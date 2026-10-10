import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fixesSafe from '../fixtures/v2/fixes_safe_sample.json'
import risk from '../fixtures/v2/risk_sample.json'
import { LangProvider } from '../i18n'
import { causeSplit } from '../risk'
import { CALENDAR, calls, makeStreet, results, serve as serveBase, settle } from '../test/server'
import StreetPlayer from '../components/street/StreetPlayer'
import Overview from './Overview'

// Grid voltage alone makes the night unsafe; solar adds the midday.
const night = risk.p_unsafe.map((_, i) => (i < 24 ? 0.9 : 0))
const nightRisk = { ...risk, p_unsafe: risk.p_unsafe.map((p, i) => Math.max(p, night[i])), p_unsafe_without_solar: night }
const serve = (body: unknown) => serveBase({ '/risk': body, '/fixes': fixesSafe })

beforeEach(() => localStorage.clear())
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks() })

describe('cause split', () => {
  it('puts what stays unsafe with every panel off in the grid part and the rest in the solar part', () => {
    const s = causeSplit({ p_unsafe: [0.9, 1, 0], p_unsafe_without_solar: [0.9, 0.2, 0] })
    expect(s.grid).toEqual([0.9, 0.2, 0])
    expect(s.solar.map((x) => Number(x.toFixed(3)))).toEqual([0, 0.8, 0])
    expect(s.solarShare).toBeCloseTo(0.8 / 1.9)
  })

  it('attributes nothing when the solar-off run is missing', () => {
    expect(causeSplit({ p_unsafe: [0.5] }).solarShare).toBeNull()
  })
})

describe('Overview', () => {
  it('opens on the real tomorrow and says in plain words what happens and which fix the physics confirms', async () => {
    const m = serve({ ...risk, p_unsafe_without_solar: risk.p_unsafe.map(() => 0) })
    render(<LangProvider><Overview /></LangProvider>)
    await settle()
    expect(calls(m, '/risk').at(-1)).toContain(`date=${CALENDAR.tomorrow}`)
    const summary = screen.getByRole('region', { name: /in plain words/i }).textContent ?? ''
    expect(summary).toContain(String(risk.expected_unsafe_hours.mean))
    expect(summary).toMatch(/rooftop solar/i)
    expect(summary).toContain(fixesSafe.outcomes.find((o) => o.id === fixesSafe.verdict.recommended)!.label)
  })

  it('names the grid as the cause when the street stays unsafe with every panel off', async () => {
    serve(nightRisk)
    render(<LangProvider><Overview /></LangProvider>)
    await settle()
    expect(screen.getByRole('region', { name: /in plain words/i }).textContent).toMatch(/grid's own voltage/i)
  })

  it('every journey card opens its page, and the checks count comes from results.json', async () => {
    serve(nightRisk)
    const go = vi.fn()
    render(<LangProvider><Overview go={go} /></LangProvider>)
    await settle()
    fireEvent.click(document.querySelector('[data-area="planning"]')!)
    expect(go).toHaveBeenCalledWith('planning')
    const passed = results.gates.filter((g) => g.status === 'pass').length
    expect(screen.getByRole('region', { name: /checks passed/i }).textContent).toContain(`${passed}/${results.gates.length}`)
  })
})

// The player is on Tomorrow and Fixes (the overview no longer embeds it, PR #28); it is tested on its own.
describe('the street player', () => {
  it('draws the transformer, the three phases and every home on its own phase', async () => {
    serve(nightRisk)
    render(<LangProvider><StreetPlayer network="benchmark_250" rule="pm10" date={CALENDAR.tomorrow} /></LangProvider>)
    await settle()
    const map = screen.getByRole('img', { name: /the street at/i })
    expect(map.querySelectorAll('[data-home]').length).toBe(2)
    expect(map.querySelectorAll('.sv-feeder-base').length).toBe(3)
    expect(map.querySelectorAll('.sv-drop.ph-a').length).toBe(1)
    expect(map.querySelectorAll('.sv-drop.ph-b').length).toBe(1)
  })

  it('at midday the solar home sends power back up phase A, goes over the limit, and the balance adds up', async () => {
    serve(nightRisk)
    render(<LangProvider><StreetPlayer network="benchmark_250" rule="pm10" date={CALENDAR.tomorrow} /></LangProvider>)
    await settle()
    fireEvent.change(screen.getByRole('slider', { name: /time of day/i }), { target: { value: '48' } })
    await settle()
    const map = screen.getByRole('img', { name: /the street at 12:00/i })
    const solarHome = map.querySelector('[data-home="0"]')!
    expect(solarHome.classList.contains('v-over')).toBe(true)
    expect(solarHome.classList.contains('exporting')).toBe(true)
    expect(map.querySelectorAll('.sv-flow.feeder')[0].classList.contains('back')).toBe(true)
    expect(screen.getByText(/solar sent back to the grid/i)).toBeTruthy()
    // from the wire flows: 3 kW solar = 0.5 kW homes + 0 lost + 2.5 kW sent back
    expect(document.querySelector('[data-numbers="balance"]')!.textContent).toMatch(/solar 3 = homes 0\.5 \+ lost 0 \+ sent back 2\.5 kW/)
    // the home itself: 3 kW of solar, 0 kW used, all of it sent back
    fireEvent.click(solarHome.querySelector('.sv-hit')!)
    const card = screen.getByRole('status')
    expect(card.textContent).toMatch(/sending back \(reverse flow\)3 kW/i)
  })

  it('play moves the clock forward and pause stops it', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    serve(nightRisk)
    render(<LangProvider><StreetPlayer network="benchmark_250" rule="pm10" date={CALENDAR.tomorrow} /></LangProvider>)
    await act(async () => { await vi.advanceTimersByTimeAsync(10) })
    const time = () => document.querySelector('.clock .time')!.textContent
    const start = time()
    fireEvent.click(screen.getByRole('button', { name: /play the day/i }))
    await act(async () => { await vi.advanceTimersByTimeAsync(1100) })
    expect(time()).not.toBe(start)
    fireEvent.click(screen.getByRole('button', { name: /pause/i }))
    const stopped = time()
    await act(async () => { await vi.advanceTimersByTimeAsync(1100) })
    expect(time()).toBe(stopped)
  })

  it('the overview ends with the labels explained, including the phases and the neutral', async () => {
    serve(nightRisk)
    render(<LangProvider><Overview /></LangProvider>)
    await settle()
    const explainer = screen.getByRole('region', { name: /what the labels mean/i })
    expect(within(explainer).getByText(/^neutral$/i)).toBeTruthy()
    expect(within(explainer).getByText('ACT')).toBeTruthy()
  })

  it('explains a high voltage at night: no solar, no reverse flow, the grid supplies it high', async () => {
    const street = makeStreet()
    street.before.home_v[0] = [258, 258]                            // midnight, solar 0, power drawn, both homes too high
    serveBase({ '/risk': nightRisk, '/fixes': fixesSafe, '/street': street })
    render(<LangProvider><StreetPlayer network="benchmark_250" rule="pm10" date={CALENDAR.tomorrow} /></LangProvider>)
    await settle()
    fireEvent.change(screen.getByRole('slider', { name: /time of day/i }), { target: { value: '0' } })
    await settle()
    expect(screen.getByRole('note').textContent).toMatch(/no reverse flow/i)
    fireEvent.change(screen.getByRole('slider', { name: /time of day/i }), { target: { value: '48' } })
    await settle()
    expect(screen.queryByText(/no reverse flow/i)).toBeNull()
  })
})
