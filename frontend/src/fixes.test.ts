import { describe, expect, it } from 'vitest'
import { bindingText } from './fixes'
import { translate, type StringKey, type Vars } from './i18n'

const t = (key: StringKey, vars?: Vars) => translate('en', key, vars)

describe('bindingText', () => {
  it('a voltage too high reads as rising to the value, above the limit', () => {
    const text = bindingText(t, { type: 'overvoltage', steps: 26, worst: { value: 1.0912, limit: 1.06 } })
    expect(text).toMatch(/up to 251 V/)
    expect(text).toContain('244 V')
  })

  it('a voltage too low reads as falling to the value, below the limit, never "up to"', () => {
    const text = bindingText(t, { type: 'undervoltage', steps: 18, worst: { value: 0.9035, limit: 0.94 } })
    expect(text).not.toMatch(/up to/)
    expect(text).toMatch(/down to 208 V/)
    expect(text).toContain('216 V')
    expect(text).toContain('18')
  })
})
