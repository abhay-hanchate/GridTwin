import { act, cleanup, render, screen, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LangProvider } from '../i18n'
import Proof from './Proof'
import type { Results } from '../api/v2types'

// The file GET /results serves (written by python -m scripts.evaluate), read directly so the test never checks a copy.
const results: Results = JSON.parse(readFileSync(resolve(import.meta.dirname, '../../../data/results/results.json'), 'utf-8'))

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }))
function serve(body: unknown = results, status = 200) {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) =>
    new URL(String(input), 'http://x').pathname === '/api/v2/results' ? json(body, status) : json({}, 503))
}
const show = async () => {
  render(<LangProvider><Proof /></LangProvider>)
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}
const gateRow = (id: string) => screen.getByRole('row', { name: new RegExp(`^${id}\\b`) })

beforeEach(() => localStorage.clear())
afterEach(cleanup)

describe('Proof', () => {
  it('lists every gate with its verdict; a failed gate renders as failed, never hidden', async () => {
    serve()
    await show()
    const table = screen.getByRole('table', { name: /gates/i })
    expect(table.querySelectorAll('tbody tr').length).toBe(results.gates.length)
    for (const g of results.gates) expect(gateRow(g.gate).getAttribute('data-status')).toBe(g.status)
    const g4 = results.gates.find((g) => g.gate === 'G4')!
    expect(g4.status).toBe('fail')
    expect(within(gateRow('G4')).getByText(/^failed$/i)).toBeTruthy()
    expect(gateRow('G4').textContent).toContain(g4.note)
  })

  it('shows the measured values and the bar each gate had to clear', async () => {
    serve()
    await show()
    const g3 = results.gates.find((g) => g.gate === 'G3')!
    expect(gateRow('G3').textContent).toContain(String((g3.measured as { mae_p50: number }).mae_p50))
    expect(gateRow('G3').textContent).toContain(g3.threshold)
  })

  it('shows the summary counts and every bake-off winner', async () => {
    serve()
    await show()
    const summary = screen.getByRole('region', { name: /summary/i }).textContent ?? ''
    expect(summary).toContain(String(results.summary.pass))
    expect(summary).toContain(String(results.summary.fail))
    const bakeoffs = screen.getByRole('table', { name: /bake-off/i })
    expect(bakeoffs.querySelectorAll('tbody tr').length).toBe(results.bakeoffs.length)
  })

  it('every number on the page exists in results.json (honesty rule)', async () => {
    serve()
    await show()
    const numbers = (text: string) => text.match(/\d+(?:\.\d+)?/g) ?? []
    const allowed = new Set(numbers(JSON.stringify(results)))
    // each text node on its own: textContent would glue neighbouring cells into numbers nobody sees
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    const shown = new Set<string>()
    for (let n = walker.nextNode(); n; n = walker.nextNode()) numbers(n.textContent ?? '').forEach((x) => shown.add(x))
    expect(shown.size).toBeGreaterThan(10)
    for (const n of shown) expect(allowed.has(n), `"${n}" is on the page but not in results.json`).toBe(true)
  })

  it('a missing results.json is an error, not an empty page', async () => {
    serve({ error: { code: 'unavailable', message: 'results.json is missing; run python -m scripts.evaluate', details: {} } }, 503)
    await show()
    expect(screen.getByRole('alert').textContent).toContain('results.json is missing')
  })
})
