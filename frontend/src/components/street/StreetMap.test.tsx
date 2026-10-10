import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { StreetLayout } from '../../api/v2types'
import StreetMap from './StreetMap'
import { matchWires } from './wires'

// Test input, not a result: transformer 0 feeds 1 -> 2 and 3; the switched run opens (1, 2) and closes a tie (3, 2).
const layout: StreetLayout = {
  root: 0, rows: 2,
  nodes: [{ id: 0, x: 0, y: 0 }, { id: 1, x: 1, y: 0 }, { id: 2, x: 2, y: 0 }, { id: 3, x: 1, y: 1 }],
  lines: [{ line: 0, from: 0, to: 1 }, { line: 1, from: 1, to: 2 }, { line: 2, from: 0, to: 3 }],
}
const switched = { line_ends: [[0, 3], [3, 2], [0, 1]], line_phase_kw: [[[3, 0, 0], [1, 0, 0], [0, 0, 0]]], line_neutral_a: [[12, 4, 0]] }

describe('StreetMap with a switching fix', () => {
  it('draws the tie dashed and the opened wire still', () => {
    const w = matchWires(layout, switched, 0)
    const { container } = render(
      <StreetMap layout={layout} homes={[]} flows={w.flows} openLines={w.open} ties={w.ties} trafoLabel="T" label="street" />,
    )
    expect(container.querySelectorAll('[data-tie]')).toHaveLength(1)
    const open = container.querySelectorAll('[data-open]')
    expect(open).toHaveLength(1)
    expect(open[0].querySelectorAll('.flow')).toHaveLength(0)
    expect(container.querySelector('[data-tie] .flow:not(.idle)')).not.toBeNull()
  })
})
