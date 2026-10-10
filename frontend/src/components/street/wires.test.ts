import { describe, expect, it } from 'vitest'
import type { StreetLayout } from '../../api/v2types'
import { matchWires, rootPhaseKw } from './wires'

// Transformer 0 feeds 1 -> 2 and 3. Switching opens (1, 2) and closes a tie (3, 2), which re-numbers the lines.
const layout: StreetLayout = {
  root: 0, rows: 2,
  nodes: [{ id: 0, x: 0, y: 0 }, { id: 1, x: 1, y: 0 }, { id: 2, x: 2, y: 0 }, { id: 3, x: 1, y: 1 }],
  lines: [{ line: 0, from: 0, to: 1 }, { line: 1, from: 1, to: 2 }, { line: 2, from: 0, to: 3 }],
}
const before = {
  line_ends: [[0, 1], [1, 2], [0, 3]],
  line_phase_kw: [[[1, 0, 0], [1, 0, 0], [2, 0, 0]]],
  line_neutral_a: [[4, 4, 8]],
}
const after = {
  line_ends: [[0, 3], [3, 2], [0, 1]],
  line_phase_kw: [[[3, 0, 0], [1, 0, 0], [0, 0, 0]]],
  line_neutral_a: [[12, 4, 0]],
}

describe('matchWires', () => {
  it('maps flows to the drawn wires by their end nodes, not by line number', () => {
    const w = matchWires(layout, after, 0)
    expect(w.flows[2].A!.kw).toBe(3)            // drawn (0, 3) is the switched network's line 0
    expect(w.flows[0].A!.kw).toBe(0)            // drawn (0, 1) is its line 2
    expect(w.open).toEqual(new Set([1]))        // drawn (1, 2) no longer exists
    expect(w.ties).toHaveLength(1)
    expect(w.ties[0]).toMatchObject({ from: 3, to: 2 })
    expect(w.ties[0].flow.A!.kw).toBe(1)
  })

  it('flips the sign when the switched tree runs a drawn wire the other way', () => {
    const reversed = { ...before, line_ends: [[0, 1], [2, 1], [0, 3]] }
    expect(matchWires(layout, reversed, 0).flows[1].A!.kw).toBe(-1)
  })

  it('without line ends, uses the line numbers of the layout', () => {
    const { line_ends: _unused, ...old } = before
    const w = matchWires(layout, old, 0)
    expect(w.flows[1].A!.kw).toBe(1)
    expect(w.open.size).toBe(0)
    expect(w.ties).toHaveLength(0)
  })
})

describe('rootPhaseKw', () => {
  it('sums the wires that leave the transformer in the run’s own network', () => {
    expect(rootPhaseKw(layout, before, 0)).toEqual([3, 0, 0])
    expect(rootPhaseKw(layout, after, 0)).toEqual([3, 0, 0])
  })
})
