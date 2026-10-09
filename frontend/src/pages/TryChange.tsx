import { useMemo, useState } from 'react'
import { useV2 } from '../api/v2'
import type { CatalogEntry, DaySummary, WhatIfResult } from '../api/v2types'
import { DEFAULT_NETWORK } from '../app/defaults'
import { useView, type ViewProps } from '../app/view'
import Controls from '../components/Controls'
import ParamForm from '../components/ParamForm'
import Prov from '../components/Prov'
import Status from '../components/Status'
import StreetProfile from '../components/StreetProfile'
import VoltageCompare from '../components/VoltageCompare'
import { one, volts } from '../format'
import { useT, type StringKey } from '../i18n'
import { choicesValid, chosen, initialChoices, paramProblem, type Choice } from '../whatif'

const NOMINAL_V = 230
// Bounds of the share of homes with solar, as POST /whatif validates them (WhatIf.adoption).
const ADOPTION = { type: 'number', minimum: 0, maximum: 1 } as const

/** Try a change (F4, P9.4): any mix of registered changes and fixes, run through the engine on the design day. */
export default function TryChange({ network = DEFAULT_NETWORK, ...props }: ViewProps) {
  const view = useView(props)
  const catalog = useV2<CatalogEntry[]>('/catalog')
  return (
    <div className="v2-page">
      <Controls view={view} />
      <Status state={catalog} />
      {catalog.data && <Form catalog={catalog.data} network={network} rule={view.rule} date={view.date} />}
    </div>
  )
}

function Form({ catalog, network, rule, date }: { catalog: CatalogEntry[]; network: string; rule: string; date: string | null }) {
  const t = useT()
  const [choices, setChoices] = useState<Record<string, Choice>>(() => initialChoices(catalog))
  const [adoption, setAdoption] = useState('1')
  const [submitted, setSubmitted] = useState<string | null>(null)
  const adoptionProblem = paramProblem(ADOPTION, adoption)
  const valid = adoptionProblem === null && choicesValid(catalog, choices)
  const result = useV2<WhatIfResult>(submitted ? '/whatif' : null, submitted ?? undefined)
  const groups = useMemo(() => (['change', 'fix'] as const).map((kind) => [kind, catalog.filter((e) => e.kind === kind)] as const), [catalog])

  const run = () => {
    if (!valid) return
    setSubmitted(JSON.stringify({
      network, rule, ...(date ? { date } : {}), adoption: Number(adoption),
      changes: chosen(catalog, choices, 'change'), fixes: chosen(catalog, choices, 'fix'),
    }))
  }

  return (
    <>
      <p className="muted">{t('try.intro')}</p>
      <form className="whatif-form" onSubmit={(e) => { e.preventDefault(); run() }}>
        <div className="param">
          <label htmlFor="adoption">{t('try.adoption', { min: ADOPTION.minimum, max: ADOPTION.maximum })}</label>
          <input id="adoption" type="number" min={ADOPTION.minimum} max={ADOPTION.maximum} step="any" value={adoption}
            aria-invalid={adoptionProblem !== null} onChange={(e) => setAdoption(e.target.value)} />
          {adoptionProblem && <span className="error" role="alert">{t('try.error_range', { min: ADOPTION.minimum, max: ADOPTION.maximum })}</span>}
        </div>
        {groups.map(([kind, entries]) => (
          <section key={kind} className="param-group">
            <h3>{t(`try.group_${kind}` as StringKey)}</h3>
            {entries.map((e) => (
              <ParamForm key={e.id} entry={e} choice={choices[e.id]}
                onChange={(c) => setChoices((all) => ({ ...all, [e.id]: c }))} />
            ))}
          </section>
        ))}
        <button type="submit" className="primary" disabled={!valid}>{t('try.run')}</button>
      </form>
      {submitted && <Status state={result} />}
      {result.data && <Outcome result={result.data} />}
    </>
  )
}

type Row = { key: StringKey; value: (s: DaySummary) => string }
const ROWS: Row[] = [
  { key: 'try.row_unsafe', value: (s) => String(s.violation_steps) },
  { key: 'try.row_peak', value: (s) => volts(s.max_vm_pu * NOMINAL_V) },
  { key: 'try.row_low', value: (s) => volts(s.min_vm_pu * NOMINAL_V) },
  { key: 'try.row_trafo', value: (s) => one(s.max_trafo_loading_pct) },
  { key: 'try.row_line', value: (s) => one(s.max_line_loading_pct) },
  { key: 'try.row_curtailed', value: (s) => one(s.curtailed_kwh) },
]

function Outcome({ result }: { result: WhatIfResult }) {
  const t = useT()
  return (
    <>
      <section className="card" data-numbers="before and after">
        <h3 id="whatif-title">{t('try.result_title')} <Prov kind="modeled" /></h3>
        <p className="muted">{t('try.result_day', { date: result.date, min: volts(result.limits_v.min), max: volts(result.limits_v.max) })}</p>
        <div className="table-scroll">
          <table className="data-table" aria-labelledby="whatif-title">
            <thead><tr><th scope="col" /><th scope="col">{t('fixes.before')}</th><th scope="col">{t('fixes.after')}</th></tr></thead>
            <tbody>
              {ROWS.map((r) => (
                <tr key={r.key}><th scope="row">{t(r.key)}</th><td>{r.value(result.before.summary)}</td><td>{r.value(result.after.summary)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <VoltageCompare voltage={{ t: result.t, before_max_v: result.before.max_v, after_max_v: result.after.max_v }}
        label={t('try.chart_name')} vmax={result.limits_v.max} />
      <StreetProfile result={result} />
    </>
  )
}
