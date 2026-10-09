import { act, cleanup, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Fixes as FixesResult, Risk } from '../api/v2types'
import rules from '../fixtures/v2/rules_sample.json'
import { LangProvider } from '../i18n'
import Fixes from './Fixes'
import Home from './Home'

// The precomputed demo results the API serves (Person A's nightly run, data/results/v2). Rendering every one of them
// is the contract test between the engine's output and the pages: a renamed or missing field fails here.
const RESULTS = resolve(import.meta.dirname, '../../../data/results/v2')
const read = (name: string) => JSON.parse(readFileSync(resolve(RESULTS, name), 'utf-8'))
const index: { entries: { route: string; key: string; date: string; rule: string }[] } = read('index.json')
const entries = (route: string) => index.entries.filter((e) => e.route === route).map((e) => [`${e.date} ${e.rule}`, e.key] as const)

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
function serve(route: string, body: unknown) {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = new URL(String(input), 'http://x')
    if (url.pathname === '/api/v2/rules') return json(rules.rules)
    if (url.pathname === `/api/v2/${route}`) return json(body)
    return Promise.resolve(new Response('{}', { status: 503 }))
  })
}
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 0)) })

afterEach(cleanup)

describe('every precomputed result renders', () => {
  it('there is at least one risk and one fixes result', () => {
    expect(entries('risk').length).toBeGreaterThan(0)
    expect(entries('fixes').length).toBeGreaterThan(0)
  })

  it.each(entries('risk'))('Home: %s', async (_, key) => {
    const risk: Risk = read(`${key}.json`)
    serve('risk', risk)
    render(<LangProvider><Home rule={risk.rule} onRule={() => {}} /></LangProvider>)
    await settle()
    expect(screen.getByRole('heading', { level: 2 }).textContent).toContain(risk.level.toUpperCase())
    expect(screen.getByRole('img', { name: /probability/i }).querySelectorAll('[data-step]').length).toBe(risk.p_unsafe.length)
  })

  it.each(entries('fixes'))('Fixes: %s', async (_, key) => {
    const fixes: FixesResult = read(`${key}.json`)
    serve('fixes', fixes)
    render(<LangProvider><Fixes rule={fixes.rule} onRule={() => {}} /></LangProvider>)
    await settle()
    if (fixes.verdict.safe_action_found) expect(screen.queryByRole('region', { name: /no safe action/i })).toBeNull()
    else expect(screen.getByRole('region', { name: /no safe action/i })).toBeTruthy()
    const table = screen.getByRole('table', { name: /every option/i })
    expect(table.querySelectorAll('tbody tr').length).toBe(fixes.outcomes.length)
  })
})
