import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LangProvider } from '../i18n'
import { results, serve, settle } from '../test/server'
import Proof from './Proof'

const show = async () => { render(<LangProvider><Proof /></LangProvider>); await settle() }
const gateCard = (id: string) => [...document.querySelectorAll('.gate-card')].find((c) => c.querySelector('.gate-id')?.textContent === id) as HTMLElement

beforeEach(() => localStorage.clear())
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('Proof', () => {
  it('shows every gate once, under the question it answers, with its verdict; failed ones stay visible', async () => {
    serve()
    await show()
    expect(document.querySelectorAll('.gate-card').length).toBe(results.gates.length)
    for (const g of results.gates) expect(gateCard(g.gate).getAttribute('data-status')).toBe(g.status)
    const failed = results.gates.filter((g) => g.status === 'fail')
    for (const g of failed) {
      expect(within(gateCard(g.gate)).getByText(/^failed$/i)).toBeTruthy()
      if (g.note) expect(gateCard(g.gate).textContent).toContain(g.note)
    }
    expect([...document.querySelectorAll('.proof-q h3')].map((h) => h.textContent)).toEqual([
      'Is the physics right?', 'Are the forecasts good?', 'Are the risk chances honest?', 'May it be used?'])
  })

  it('keeps the measured values and the bar each gate had to clear in its details', async () => {
    serve()
    await show()
    const g3 = results.gates.find((g) => g.gate === 'G3')!
    expect(gateCard('G3').textContent).toContain(String((g3.measured as { mae_p50: number }).mae_p50))
    expect(gateCard('G3').textContent).toContain(g3.threshold)
  })

  it('shows the score and every bake-off', async () => {
    serve()
    await show()
    const summary = screen.getByRole('region', { name: /summary/i }).textContent ?? ''
    expect(summary).toContain(String(results.summary.pass))
    const bakeoffs = screen.getByRole('table', { name: /bake-off/i })
    expect(bakeoffs.querySelectorAll('tbody tr').length).toBe(results.bakeoffs.length)
  })

  it('every number on the page exists in results.json (honesty rule)', async () => {
    serve()
    await show()
    const numbers = (text: string) => text.match(/\d+(?:\.\d+)?/g) ?? []
    const allowed = new Set([...numbers(JSON.stringify(results)), ...numbers(`${results.gates.length}`)])
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    const shown = new Set<string>()
    for (let n = walker.nextNode(); n; n = walker.nextNode()) numbers(n.textContent ?? '').forEach((x) => shown.add(x))
    expect(shown.size).toBeGreaterThan(10)
    for (const n of shown) expect(allowed.has(n), `"${n}" is on the page but not in results.json`).toBe(true)
  })

  it('a missing results.json is an error, not an empty page', async () => {
    serve({ '/results': { error: { code: 'unavailable', message: 'results.json is missing; run python -m scripts.evaluate', details: {} } } },
      { status: { '/results': 503 } })
    await show()
    expect(screen.getByRole('alert').textContent).toContain('results.json is missing')
  })
})
