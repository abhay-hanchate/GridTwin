import { describe, expect, it } from 'vitest'
import { change } from './format'

describe('change', () => {
  it('signs a voltage change: minus when it falls, plus when it rises, never a double sign', () => {
    expect(change(-2.94)).toBe('−2.9')
    expect(change(0.4)).toBe('+0.4')
    expect(change(0)).toBe('0')
  })
})
