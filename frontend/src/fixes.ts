import type { BindingLimit } from './api/v2types'
import { one, volts } from './format'
import type { StringKey, Vars } from './i18n'

type T = (key: StringKey, vars?: Vars) => string
const NOMINAL_V = 230

/** The binding limit in words: voltages in volts, loadings in percent, solver failures as such. */
export function bindingText(t: T, limit: BindingLimit): string {
  const name = t(`limit.${limit.type}` as StringKey)
  if (limit.type === 'overvoltage' || limit.type === 'undervoltage') {
    return t('fixes.binding_voltage', { limit: name, value: volts(limit.worst.value * NOMINAL_V),
      bound: volts(limit.worst.limit * NOMINAL_V), steps: limit.steps })
  }
  if (limit.type === 'solver_failure') return t('fixes.binding_solver', { steps: limit.steps })
  return t('fixes.binding_loading', { limit: name, value: one(limit.worst.value), bound: one(limit.worst.limit), steps: limit.steps })
}
