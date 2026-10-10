import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import catalog from '../fixtures/v2/catalog.json'
import whatif from '../fixtures/v2/whatif_sample.json'
import { LangProvider } from '../i18n'
import { serve as serveBase, settle } from '../test/server'
import TryChange from './TryChange'

const AFTER = { ...whatif.after, summary: { ...whatif.after.summary, violation_steps: 12, max_vm_pu: 1.05 } }
const serve = (offline = false) => serveBase({
  '/catalog': catalog,
  '/whatif': (_: URL, init?: RequestInit) => (init?.method === 'POST' ? { ...whatif, after: AFTER } : {}),
}, { offline })
const posts = (m: ReturnType<typeof serve>) => m.mock.calls.filter((c) => c[1]?.method === 'POST')
const show = async (rule = 'up_2005') => { render(<LangProvider><TryChange rule={rule} onRule={() => {}} /></LangProvider>); await settle() }
const card = (id: string) => document.querySelector(`[data-entry="${id}"]`) as HTMLElement
const toggle = (id: string) => fireEvent.click(within(card(id)).getByRole('switch'))
const run = () => screen.getByRole('button', { name: /^run/i }) as HTMLButtonElement

beforeEach(() => localStorage.clear())
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('What if', () => {
  it('says what the page is for before asking for anything', async () => {
    serve()
    await show()
    expect(document.querySelectorAll('.usecase > div').length).toBe(3)
  })

  it('has one card per catalog item, each parameter a slider within its bounds', async () => {
    serve()
    await show()
    for (const e of catalog) expect(card(e.id)).not.toBeNull()
    const kw = within(card('fix.battery')).getAllByRole('slider')[0] as HTMLInputElement
    expect(kw.type).toBe('range')
    expect([kw.max, kw.value]).toEqual(['500', '50'])
    const tap = within(card('fix.tap')).getByRole('slider') as HTMLInputElement
    expect([tap.min, tap.max, tap.step]).toEqual(['-2', '2', '1'])
    expect(tap.disabled).toBe(true)
  })

  it('nothing can run until a change or fix is switched on', async () => {
    const m = serve()
    await show()
    expect(run().disabled).toBe(true)
    fireEvent.click(run())
    await settle()
    expect(posts(m).length).toBe(0)
  })

  it('a preset switches on its change with its values', async () => {
    serve()
    await show()
    fireEvent.click(screen.getByRole('button', { name: /electric cars/i }))
    await settle()
    expect(within(card('change.ev_charging')).getByRole('switch').getAttribute('aria-checked')).toBe('true')
    expect((within(card('change.ev_charging')).getAllByRole('slider')[0] as HTMLInputElement).value).toBe('0.5')
  })

  it('runs the chosen changes and fixes and shows each number before and after', async () => {
    const m = serve()
    await show()
    toggle('change.heatwave')
    toggle('fix.tap')
    fireEvent.click(run())
    await settle()
    const sent = JSON.parse(String(posts(m)[0][1]!.body))
    expect(sent.changes).toEqual([{ id: 'change.heatwave', params: { load_factor: 1.3 } }])
    expect(sent.fixes).toEqual([{ id: 'fix.tap', params: { tap_pos: 1 } }])
    expect(sent.rule).toBe('up_2005')
    const result = screen.getByRole('region', { name: /before and after/i }).textContent ?? ''
    expect(result).toContain(String(whatif.before.summary.violation_steps))
    expect(result).toContain('12')
    expect(result).toContain(String(Math.round(1.05 * 230)))
    expect(screen.getByRole('img', { name: /highest voltage of the day/i })).toBeTruthy()
  })

  it('a result is never shown under a rule it was not computed for', async () => {
    serve()
    const { rerender } = render(<LangProvider><TryChange rule="up_2005" onRule={() => {}} /></LangProvider>)
    await settle()
    toggle('change.heatwave')
    fireEvent.click(run())
    await settle()
    expect(screen.getByRole('region', { name: /before and after/i })).toBeTruthy()
    rerender(<LangProvider><TryChange rule="pm10" onRule={() => {}} /></LangProvider>)
    await settle()
    expect(screen.queryByRole('region', { name: /before and after/i })).toBeNull()
  })

  it('in offline mode it says what-if needs the live engine and does not run', async () => {
    const m = serve(true)
    await show()
    expect(screen.getByRole('note').textContent).toContain('GRIDTWIN_OFFLINE=0')
    toggle('change.heatwave')
    expect(run().disabled).toBe(true)
    expect(posts(m).length).toBe(0)
  })

  it('compares with the street as it is today, and shows the changes alone when fixes are added too', async () => {
    const today = { ...whatif.before, summary: { ...whatif.before.summary, violation_steps: 3 } }
    const m = serveBase({ '/catalog': catalog, '/whatif': (_: URL, init?: RequestInit) =>
      (init?.method === 'POST' ? { ...whatif, fixes: ['fix.tap'], today, after: AFTER } : {}) })
    await show()
    toggle('change.heatwave')
    toggle('fix.tap')
    fireEvent.click(run())
    await settle()
    expect(posts(m).length).toBe(1)
    const unsafe = [...document.querySelectorAll('.stat')].find((el) => /unsafe/i.test(el.textContent ?? ''))!
    expect(unsafe.textContent).toContain('was 3')
    expect(unsafe.textContent).toContain(`with the changes but no fix: ${whatif.before.summary.violation_steps}`)
  })
})
