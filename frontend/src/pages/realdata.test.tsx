import { cleanup, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Fixes as FixesResult, Risk, Street } from '../api/v2types'
import { LangProvider } from '../i18n'
import { serve, settle } from '../test/server'
import Fixes from './Fixes'
import Forecast from './Forecast'
import StreetPlayer from '../components/street/StreetPlayer'

// The precomputed results the API serves (the nightly run, data/results/v2). Rendering every one of them is the
// contract test between the engine's output and the pages: a renamed or missing field fails here.
const RESULTS = resolve(import.meta.dirname, '../../../data/results/v2')
const read = (name: string) => JSON.parse(readFileSync(resolve(RESULTS, name), 'utf-8'))
const index: { entries: { route: string; key: string; date: string; rule: string }[] } = read('index.json')
const entries = (route: string) => index.entries.filter((e) => e.route === route).map((e) => [`${e.date} ${e.rule}`, e.key] as const)
const verdictHeading = () => document.querySelector('h2.verdict') as HTMLElement

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('every precomputed result renders', () => {
  it('there is at least one risk and one fixes result', () => {
    expect(entries('risk').length).toBeGreaterThan(0)
    expect(entries('fixes').length).toBeGreaterThan(0)
  })

  it.each(entries('risk'))('Tomorrow: %s', async (_, key) => {
    const risk: Risk = read(`${key}.json`)
    serve({ '/risk': risk })
    render(<LangProvider><Forecast rule={risk.rule} onRule={() => {}} date={risk.date} /></LangProvider>)
    await settle()
    expect(verdictHeading().textContent).toContain(risk.level.toUpperCase())
    expect(screen.getByRole('img', { name: /probability/i }).querySelectorAll('[data-step]').length).toBe(risk.p_unsafe.length)
  })

  it.each(entries('fixes'))('Fixes: %s', async (_, key) => {
    const fixes: FixesResult = read(`${key}.json`)
    serve({ '/fixes': fixes })
    render(<LangProvider><Fixes rule={fixes.rule} onRule={() => {}} date={fixes.date} /></LangProvider>)
    await settle()
    if (fixes.verdict.safe_action_found) expect(screen.queryByRole('region', { name: /no safe/i })).toBeNull()
    else expect(screen.getByRole('region', { name: /no safe/i })).toBeTruthy()
    expect(document.querySelectorAll('[data-fix]').length).toBe(fixes.outcomes.length)
  })

  it.each(entries('street'))('Street: %s', async (_, key) => {
    const street: Street = read(`${key}.json`)
    serve({ '/street': street })
    render(<LangProvider><StreetPlayer network={street.network} rule={street.rule} date={street.date} fix={street.fix} /></LangProvider>)
    await settle()
    const map = screen.getByRole('img', { name: /the street at/i })
    expect(map.querySelectorAll('[data-home]').length).toBe(street.homes.length)
    expect(map.querySelectorAll('.flow').length).toBe(street.layout.lines.length * 4)
  })
})
