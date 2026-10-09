import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import catalog from '../fixtures/v2/catalog.json'
import rules from '../fixtures/v2/rules_sample.json'
import whatif from '../fixtures/v2/whatif_sample.json'
import { LangProvider } from '../i18n'
import TryChange from './TryChange'

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
const AFTER = { ...whatif.after, summary: { ...whatif.after.summary, violation_steps: 12, max_vm_pu: 1.05 } }

function serve() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = new URL(String(input), 'http://x')
    if (url.pathname === '/api/v2/rules') return json(rules.rules)
    if (url.pathname === '/api/v2/catalog') return json(catalog)
    if (url.pathname === '/api/v2/whatif' && init?.method === 'POST') return json({ ...whatif, after: AFTER })
    return Promise.resolve(new Response('{}', { status: 503 }))
  })
}
const posts = (m: ReturnType<typeof serve>) => m.mock.calls.filter((c) => c[1]?.method === 'POST')
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 0)) })
const show = async () => { render(<LangProvider><TryChange rule="up_2005" onRule={() => {}} /></LangProvider>); await settle() }
const entry = (id: string) => screen.getByRole('group', { name: catalog.find((e) => e.id === id)!.label })

beforeEach(() => localStorage.clear())
afterEach(cleanup)

describe('Try a change', () => {
  it('the form has one entry per catalog item and every parameter with its bounds', async () => {
    serve()
    await show()
    for (const e of catalog) expect(entry(e.id)).toBeTruthy()
    const battery = within(entry('fix.battery'))
    const kw = battery.getByRole('spinbutton', { name: /^kw$/i }) as HTMLInputElement
    expect(kw.max).toBe('500')
    expect(kw.value).toBe('50')
    const tap = within(entry('fix.tap')).getByRole('spinbutton') as HTMLInputElement
    expect([tap.min, tap.max, tap.step]).toEqual(['-2', '2', '1'])
  })

  it('invalid input is blocked before the request', async () => {
    const fetchMock = serve()
    await show()
    const box = within(entry('change.panel_size'))
    fireEvent.click(box.getByRole('checkbox'))
    fireEvent.change(box.getByRole('spinbutton'), { target: { value: '25' } })
    expect(box.getByRole('alert').textContent).toMatch(/10/)
    const run = screen.getByRole('button', { name: /run/i }) as HTMLButtonElement
    expect(run.disabled).toBe(true)
    fireEvent.click(run)
    await settle()
    expect(posts(fetchMock).length).toBe(0)
  })

  it('a zero battery size is invalid (the bound is exclusive)', async () => {
    serve()
    await show()
    const box = within(entry('fix.battery'))
    fireEvent.click(box.getByRole('checkbox'))
    fireEvent.change(box.getByRole('spinbutton', { name: /^kw$/i }), { target: { value: '0' } })
    expect(box.getByRole('alert')).toBeTruthy()
  })

  it('runs the chosen changes and fixes and shows unsafe quarter hours and peak voltage before and after', async () => {
    const fetchMock = serve()
    await show()
    fireEvent.click(within(entry('change.heatwave')).getByRole('checkbox'))
    fireEvent.click(within(entry('fix.tap')).getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
    await settle()
    const sent = JSON.parse(String(posts(fetchMock)[0][1]!.body))
    expect(sent.changes).toEqual([{ id: 'change.heatwave', params: { load_factor: 1.3 } }])
    expect(sent.fixes).toEqual([{ id: 'fix.tap', params: { tap_pos: 1 } }])
    expect(sent.rule).toBe('up_2005')
    const table = screen.getByRole('table', { name: /before and after/i })
    expect(table.textContent).toContain(String(whatif.before.summary.violation_steps))
    expect(table.textContent).toContain('12')
    expect(table.textContent).toContain(String(Math.round(whatif.before.summary.max_vm_pu * 230)))
    expect(table.textContent).toContain(String(Math.round(1.05 * 230)))
    expect(screen.getByRole('img', { name: /along the street/i })).toBeTruthy()
  })
})
