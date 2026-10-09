import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import connections from '../fixtures/v2/connection_samples.json'
import headroom from '../fixtures/v2/headroom_sample.json'
import hosting from '../fixtures/v2/hosting_sample.json'
import rules from '../fixtures/v2/rules_sample.json'
import { LangProvider } from '../i18n'
import Planning from './Planning'

type Decision = 'approve' | 'approve_with_conditions' | 'refuse'
const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))

function serve(decision: Decision = 'approve') {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = new URL(String(input), 'http://x')
    if (url.pathname === '/api/v2/rules') return json(rules.rules)
    if (url.pathname === '/api/v2/headroom') return json(headroom)
    if (url.pathname === '/api/v2/hosting') return json(hosting)
    if (url.pathname === '/api/v2/connection-check' && init?.method === 'POST') return json(connections[decision])
    return Promise.resolve(new Response('{}', { status: 503 }))
  })
}
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 0)) })
const show = async () => { render(<LangProvider><Planning rule="up_2005" onRule={() => {}} /></LangProvider>); await settle() }
const check = async () => { fireEvent.click(screen.getByRole('button', { name: /check/i })); await settle() }
const decisionText = () => screen.getByRole('region', { name: /decision/i }).textContent ?? ''

beforeEach(() => localStorage.clear())
afterEach(cleanup)

describe('Planning: headroom and hosting capacity', () => {
  it('shows headroom per location and phase beside the flat state caps, each cap marked as not verified', async () => {
    serve()
    await show()
    const table = screen.getByRole('table', { name: /headroom/i })
    expect(table.querySelectorAll('tbody tr').length).toBe(2 * 3)
    expect(table.textContent).toContain(String(headroom.locations.near.phases.B.no_worse_kw))
    const caps = screen.getByRole('table', { name: /state caps/i })
    expect(caps.querySelectorAll('tbody tr').length).toBe(Object.keys(headroom.flat_caps).length)
    expect(caps.textContent).toContain('not verified')
  })

  it('shows hosting capacity P10, P50 and P90 without a fix and with Volt/VAR', async () => {
    serve()
    await show()
    const card = screen.getByRole('region', { name: /hosting capacity/i })
    const bars = card.querySelectorAll('[data-hosting]')
    expect(bars.length).toBe(2)
    expect(bars[0].textContent).toContain(`${Math.round(hosting.without_fix.adoption_share.p50 * 100)}%`)
    expect(bars[1].textContent).toContain(`${Math.round(hosting.with_volt_var.adoption_share.p50 * 100)}%`)
  })
})

describe('Planning: connection check', () => {
  it('sends the request with node, size, count, phase, rule and day', async () => {
    const fetchMock = serve()
    await show()
    fireEvent.change(screen.getByLabelText(/size/i), { target: { value: '5' } })
    fireEvent.change(screen.getByLabelText(/^phase$/i), { target: { value: 'B' } })
    await check()
    const post = fetchMock.mock.calls.find((c) => c[1]?.method === 'POST')!
    const body = JSON.parse(String(post[1]!.body))
    expect(body).toMatchObject({ node: headroom.locations.far.node, kw: 5, count: 1, phase: 'B', rule: 'up_2005' })
  })

  it('the three decisions render distinct wording', async () => {
    const texts: string[] = []
    for (const d of ['approve', 'approve_with_conditions', 'refuse'] as const) {
      serve(d)
      await show()
      await check()
      texts.push(decisionText())
      cleanup()
      vi.restoreAllMocks()
    }
    expect(new Set(texts.map((x) => x.split(':')[0])).size).toBe(3)
    expect(texts[1]).toContain(connections.approve_with_conditions.conditions[0])
  })

  it('a refusal shows the binding limit and the largest size that passes', async () => {
    serve('refuse')
    await show()
    await check()
    const text = decisionText()
    expect(text).toContain('over-voltage')
    expect(text).toContain(String(Math.round(connections.refuse.binding_limit!.worst.value * 230)))
    expect(text).toContain(String(connections.refuse.largest_kw_that_passes))
  })

  it('a size outside 0 to 50 kW is blocked before the request', async () => {
    const fetchMock = serve()
    await show()
    fireEvent.change(screen.getByLabelText(/size/i), { target: { value: '80' } })
    expect((screen.getByRole('button', { name: /check/i }) as HTMLButtonElement).disabled).toBe(true)
    expect(fetchMock.mock.calls.some((c) => c[1]?.method === 'POST')).toBe(false)
  })
})
