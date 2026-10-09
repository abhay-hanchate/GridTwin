import { readFileSync } from 'node:fs'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import en from '../i18n/en.json'
import hi from '../i18n/hi.json'
import { LangProvider } from '../i18n'
import { Shell } from './Shell'

const ui = () => render(<LangProvider><Shell render={(area) => <p>page {area}</p>} /></LangProvider>)

beforeEach(() => localStorage.clear())
afterEach(cleanup)

describe('Shell', () => {
  it('switching language changes the tab labels', () => {
    ui()
    expect(screen.getByRole('tab', { name: en['area.home'] })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'हिन्दी' }))
    expect(screen.queryByRole('tab', { name: en['area.home'] })).toBeNull()
    expect(screen.getByRole('tab', { name: hi['area.home'] })).toBeTruthy()
    expect(document.documentElement.lang).toBe('hi')
  })

  it('remembers the chosen language across reloads', () => {
    ui()
    fireEvent.click(screen.getByRole('button', { name: 'हिन्दी' }))
    cleanup()
    ui()
    expect(screen.getByRole('tab', { name: hi['area.fixes'] })).toBeTruthy()
  })

  it('arrow keys move between areas and show the matching page', () => {
    ui()
    const home = screen.getByRole('tab', { name: en['area.home'] })
    expect(screen.getByText('page home')).toBeTruthy()
    fireEvent.keyDown(home, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: en['area.try'] }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('page try')).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('tab', { name: en['area.try'] }), { key: 'End' })
    expect(screen.getByText('page proof')).toBeTruthy()
  })

  it('has a skip link to the content', () => {
    ui()
    expect(screen.getByText(en['shell.skip']).getAttribute('href')).toBe('#content')
  })
})

describe('strings', () => {
  it('Hindi has every English key, and no string hard-codes a number', () => {
    expect(Object.keys(hi).sort()).toEqual(Object.keys(en).sort())
    for (const dict of [en, hi]) {
      for (const [key, text] of Object.entries(dict)) {
        // numbers come from the API or results.json through {placeholders}, never from the strings (honesty rule)
        // (quantile names such as P10 and P90 are labels, not values)
        expect(text.replace(/\{[a-z_]+\}/g, '').replace(/\bP[159]0\b/g, ''), key).not.toMatch(/[0-9०-९]/)
      }
    }
  })
})

describe('phone layout at 360 px', () => {
  const css = readFileSync('src/index.css', 'utf8')

  it('uses 16 px side gutters on a phone', () => {
    const phone = css.match(/@media \(max-width: 560px\) \{([\s\S]*?)\n\}/)
    expect(phone).not.toBeNull()
    expect(phone![1]).toMatch(/\.app \{ padding: \d+px 16px \d+px; \}/)
  })

  it('has no fixed width wider than the 328 px a phone leaves between the gutters', () => {
    const widths = [...css.matchAll(/(?:^|[;{\s])(?:min-)?width:\s*(\d+)px/g)].map((m) => Number(m[1]))
    expect(widths.length).toBeGreaterThan(0)
    expect(Math.max(...widths)).toBeLessThanOrEqual(328)
  })
})
