import { useState } from 'react'
import { useV2 } from '../api/v2'
import type { Results, Rule } from '../api/v2types'
import { DEFAULT_RULE } from './defaults'

/** What a page is looking at. Owned by the caller (shared across pages) or, if not passed, by the page itself. */
export type ViewProps = {
  network?: string
  rule?: string
  onRule?: (id: string) => void
  date?: string | null              // null: the latest precomputed day (the API's default)
  onDate?: (date: string) => void
}

export interface DemoDay { date: string; dayType: string }

/** The days the nightly run precomputed, in date order (from results.json, never hard-coded). */
export function demoDays(results: Results | null): DemoDay[] {
  const seen = new Map<string, string>()
  for (const r of results?.headlines.demo?.results ?? []) if (!seen.has(r.date)) seen.set(r.date, r.day_type)
  return [...seen].sort(([a], [b]) => a.localeCompare(b)).map(([date, dayType]) => ({ date, dayType }))
}

export function useView({ rule: ruleProp, onRule, date: dateProp, onDate }: ViewProps) {
  const [ownRule, setOwnRule] = useState(DEFAULT_RULE)
  const [ownDate, setOwnDate] = useState<string | null>(null)
  const rules = useV2<Rule[]>('/rules')
  const results = useV2<Results>('/results')
  const rule = ruleProp ?? ownRule
  return {
    rule,
    setRule: onRule ?? setOwnRule,
    date: dateProp === undefined ? ownDate : dateProp,
    setDate: onDate ?? setOwnDate,
    rules,
    band: rules.data?.find((r) => r.id === rule),
    days: demoDays(results.data),
  }
}

export type View = ReturnType<typeof useView>
