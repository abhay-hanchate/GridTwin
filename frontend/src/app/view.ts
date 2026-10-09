import { useState } from 'react'
import { useV2 } from '../api/v2'
import type { Results, Rule } from '../api/v2types'
import { DEFAULT_RULE } from './defaults'

/** What a page is looking at. Owned by the caller (shared across pages) or, if not passed, by the page itself. */
export type ViewProps = {
  network?: string
  rule?: string
  onRule?: (id: string) => void
  date?: string | null              // null: the latest precomputed day
  onDate?: (date: string) => void
}

export interface DemoDay { date: string; dayType: string }

/** The days the nightly run precomputed `route` for, in date order (from results.json, never hard-coded). */
export function demoDays(results: Results | null, route?: string): DemoDay[] {
  const seen = new Map<string, string>()
  for (const r of results?.headlines.demo?.results ?? []) {
    if ((route === undefined || r.route === route) && !seen.has(r.date)) seen.set(r.date, r.day_type)
  }
  return [...seen].sort(([a], [b]) => a.localeCompare(b)).map(([date, dayType]) => ({ date, dayType }))
}

/** The day to ask `route` for: the chosen one if it was precomputed, otherwise the latest one that was. */
export function dayFor(days: DemoDay[], date: string | null): string | null {
  if (days.length === 0) return date
  return date !== null && days.some((d) => d.date === date) ? date : days[days.length - 1].date
}

/** `route` names the API route the page reads; only days precomputed for it are offered and requested. */
export function useView({ rule: ruleProp, onRule, date: dateProp, onDate }: ViewProps, route: string) {
  const [ownRule, setOwnRule] = useState(DEFAULT_RULE)
  const [ownDate, setOwnDate] = useState<string | null>(null)
  const rules = useV2<Rule[]>('/rules')
  const results = useV2<Results>('/results')
  const rule = ruleProp ?? ownRule
  const days = demoDays(results.data, route)
  const chosen = dateProp === undefined ? ownDate : dateProp
  return {
    rule,
    setRule: onRule ?? setOwnRule,
    // Hold requests until the list of precomputed days is known (or failed), so no job starts for a wrong day.
    ready: results.status === 'done' || results.status === 'error',
    date: dayFor(days, chosen),
    setDate: onDate ?? setOwnDate,
    rules,
    band: rules.data?.find((r) => r.id === rule),
    days,
  }
}

export type View = ReturnType<typeof useView>
