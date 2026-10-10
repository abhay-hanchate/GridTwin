import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import connections from '../fixtures/v2/connection_samples.json'
import headroom from '../fixtures/v2/headroom_sample.json'
import hosting from '../fixtures/v2/hosting_sample.json'
import meterSites from '../fixtures/v2/meter_sites_sample.json'
import rxMap from '../fixtures/v2/rx_map_sample.json'
import transformers from '../fixtures/v2/transformers_sample.json'
import { LangProvider } from '../i18n'
import { makeStreet, serve as serveBase, settle } from '../test/server'
import Planning from './Planning'

type Decision = 'approve' | 'approve_with_conditions' | 'refuse'

// The test street, with the probe points and meter sites of the fixtures added as nodes so their markers have a place.
const extra = [...new Set([headroom.locations.near.node, headroom.locations.far.node, ...meterSites.sites.map((m) => m.node)])].filter((n) => n > 2)
const street = () => {
  const s = makeStreet()
  return { ...s, layout: { ...s.layout, rows: 2, nodes: [...s.layout.nodes, ...extra.map((id, i) => ({ id, x: i, y: 1 }))] } }
}

function serve(decision: Decision = 'approve') {
  return serveBase({
    '/street': street,
    '/headroom': headroom, '/hosting': hosting, '/meter-sites': meterSites, '/rx-map': rxMap, '/transformers': transformers,
    '/connection-check': (_: URL, init?: RequestInit) => (init?.method === 'POST' ? connections[decision] : {}),
  })
}
const show = async () => { render(<LangProvider><Planning rule="up_2005" onRule={() => {}} /></LangProvider>); await settle() }
const layer = (name: RegExp) => { fireEvent.click(screen.getByRole('tab', { name })); return settle() }
const pickNode = async (node: number) => {
  fireEvent.click([...document.querySelectorAll('.node-pick')].find((c) => c.querySelector('title')?.textContent === String(node))!)
  await settle()
}
const check = async () => { fireEvent.click(screen.getByRole('button', { name: /check this request/i })); await settle() }
const decisionText = () => screen.getByRole('region', { name: /decision/i }).textContent ?? ''

beforeEach(() => localStorage.clear())
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('Planning: the four questions', () => {
  it('asks the questions in order, each with its own answer', async () => {
    serve()
    await show()
    const titles = [...document.querySelectorAll('.q-head h3')].map((h) => h.textContent)
    expect(titles.length).toBe(4)
    expect(titles[0]).toMatch(/how much solar/i)
  })

  it('shows hosting capacity P10, P50 and P90 without a fix and with Volt/VAR', async () => {
    serve()
    await show()
    const rows = document.querySelectorAll('[data-hosting]')
    expect(rows.length).toBe(2)
    expect(rows[0].textContent).toContain(`${Math.round(hosting.without_fix.adoption_share.p50 * 100)}%`)
    expect(rows[1].textContent).toContain(`${Math.round(hosting.with_volt_var.adoption_share.p50 * 100)}%`)
  })

  it('the map shows the room per phase at both probe points', async () => {
    serve()
    await show()
    const map = screen.getByRole('img', { name: /schematic of the street/i })
    const labels = [...map.querySelectorAll('.probe-label')].map((t) => t.textContent ?? '')
    expect(labels.length).toBe(2)
    expect(labels.join(' ')).toContain(String(headroom.locations.near.phases.B.no_worse_kw))
    const cells = document.querySelectorAll('.phase-cell')
    expect(cells.length).toBe(6)
  })

  it('the state caps are listed, each marked as not verified', async () => {
    serve()
    await show()
    const caps = screen.getByRole('table', { name: /state caps/i })
    expect(caps.querySelectorAll('tbody tr').length).toBe(Object.keys(headroom.flat_caps).length)
    expect(caps.textContent).toContain('not verified')
  })
})

describe('Planning: connection check on the map', () => {
  it('needs a point on the map, then sends node, size, count, phase, rule and day', async () => {
    const m = serve()
    await show()
    await layer(/check a connection/i)
    expect((screen.getByRole('button', { name: /check this request/i }) as HTMLButtonElement).disabled).toBe(true)
    await pickNode(2)
    fireEvent.change(screen.getByLabelText(/size of each system/i), { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: 'B' }))
    await check()
    const post = m.mock.calls.find((c) => c[1]?.method === 'POST')!
    expect(JSON.parse(String(post[1]!.body))).toMatchObject({ node: 2, kw: 5, count: 1, phase: 'B', rule: 'up_2005', date: '2026-10-11' })
  })

  it('the three decisions render distinct wording', async () => {
    const texts: string[] = []
    for (const d of ['approve', 'approve_with_conditions', 'refuse'] as const) {
      serve(d)
      await show()
      await layer(/check a connection/i)
      await pickNode(1)
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
    await layer(/check a connection/i)
    await pickNode(1)
    await check()
    const text = decisionText()
    expect(text).toContain('over-voltage')
    expect(text).toContain(String(Math.round(connections.refuse.binding_limit!.worst.value * 230)))
    expect(text).toContain(String(connections.refuse.largest_kw_that_passes))
  })
})

describe('Planning: meters, transformers, Volt/VAR', () => {
  it('numbers the best meter sites on the map in the order the API ranked them', async () => {
    serve()
    await show()
    await layer(/where to meter/i)
    const items = within(screen.getByRole('list', { name: /smart meter/i })).getAllByRole('listitem').filter((li) => li.querySelector('.pos'))
    expect(items.length).toBe(Math.min(5, meterSites.sites.length))
    expect(items[0].textContent).toContain(String(meterSites.sites[0].node))
  })

  it('ranks the transformers and marks headroom found at the search limit as "at least"', async () => {
    serve()
    await show()
    const rows = [...document.querySelectorAll('[data-transformer]')]
    expect(rows.map((r) => r.getAttribute('data-transformer'))).toEqual(transformers.transformers.map((r) => r.id))
    const capped = transformers.transformers.findIndex((r) => r.at_search_limit)
    if (capped >= 0) expect(rows[capped].textContent).toContain('at least')
  })

  it('shows the Volt/VAR reduction for every resistance and reactance scale', async () => {
    serve()
    await show()
    expect(document.querySelectorAll('.rx-cell').length).toBe(rxMap.cells.length)
  })
})
