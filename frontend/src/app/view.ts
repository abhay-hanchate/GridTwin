import { useState } from 'react'
import { useV2 } from '../api/v2'
import type { Calendar, Rule } from '../api/v2types'
import { DEFAULT_RULE } from './defaults'

/** What a page is looking at. Owned by the caller (shared across pages) or, if not passed, by the page itself. */
export type ViewProps = {
  network?: string
  rule?: string
  onRule?: (id: string) => void
  date?: string | null              // null: the default day (tomorrow, or the latest computed day when offline)
  onDate?: (date: string) => void
}

/** The day to show: the chosen one; else the real tomorrow; offline, the latest day that was computed. */
export function dayFor(calendar: Calendar | null, chosen: string | null): string | null {
  if (!calendar) return chosen
  if (calendar.offline) {
    if (chosen && calendar.ready.includes(chosen)) return chosen
    return calendar.ready.at(-1) ?? chosen
  }
  return chosen ?? calendar.tomorrow
}

export function useView({ rule: ruleProp, onRule, date: dateProp, onDate }: ViewProps, _route?: string) {
  void _route
  const [ownRule, setOwnRule] = useState(DEFAULT_RULE)
  const [ownDate, setOwnDate] = useState<string | null>(null)
  const rules = useV2<Rule[]>('/rules')
  const calendar = useV2<Calendar>('/calendar')
  const rule = ruleProp ?? ownRule
  const chosen = dateProp === undefined ? ownDate : dateProp
  return {
    rule,
    setRule: onRule ?? setOwnRule,
    // Hold requests until the calendar is known (or failed), so no job starts for a day that is then replaced.
    ready: calendar.status === 'done' || calendar.status === 'error',
    date: dayFor(calendar.data, chosen),
    setDate: onDate ?? setOwnDate,
    rules,
    band: rules.data?.find((r) => r.id === rule),
    calendar: calendar.data,
  }
}

export type View = ReturnType<typeof useView>
