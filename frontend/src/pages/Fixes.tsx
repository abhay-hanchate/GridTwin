import { useState } from 'react'
import { useV2, v2Path } from '../api/v2'
import type { Fixes as FixesResult, Outcome, Rule, Verdict } from '../api/v2types'
import { DEFAULT_NETWORK, DEFAULT_RULE } from '../app/defaults'
import Envelope from '../components/Envelope'
import FixCard from '../components/FixCard'
import PhasePlan from '../components/PhasePlan'
import Prov from '../components/Prov'
import RuleSelector from '../components/RuleSelector'
import Status from '../components/Status'
import VoltageCompare from '../components/VoltageCompare'
import { bindingText } from '../fixes'
import { one } from '../format'
import { useT, type StringKey } from '../i18n'

type Props = { network?: string; rule?: string; onRule?: (id: string) => void }

/** The ranked tournament and the honest verdict (D2, D7). */
export default function Fixes({ network = DEFAULT_NETWORK, rule: ruleProp, onRule }: Props) {
  const [ownRule, setOwnRule] = useState(DEFAULT_RULE)
  const rule = ruleProp ?? ownRule
  const setRule = onRule ?? setOwnRule
  const rules = useV2<Rule[]>('/rules')
  const fixes = useV2<FixesResult>(v2Path('/fixes', { network, rule }))
  const band = rules.data?.find((r) => r.id === rule)
  return (
    <div className="v2-page">
      {rules.data ? <RuleSelector rules={rules.data} value={rule} onChange={setRule} /> : <Status state={rules} />}
      <Status state={fixes} />
      {fixes.data && <FixesView result={fixes.data} vmax={band?.vmax_v} />}
    </div>
  )
}

function FixesView({ result, vmax }: { result: FixesResult; vmax?: number }) {
  const t = useT()
  const v = result.verdict
  const byId = new Map(result.outcomes.map((o) => [o.id, o]))
  // The fix whose details are shown: the recommended one, or (if nothing is safe) the closest one.
  const focus = byId.get((v.safe_action_found ? v.recommended : v.closest) ?? '')
  return (
    <>
      <p className="muted" data-numbers="baseline">
        {t('fixes.baseline', { steps: v.baseline_unsafe_steps ?? result.baseline_unsafe_steps })} <Prov kind="modeled" />
      </p>
      {v.safe_action_found && focus ? <FixCard outcome={focus} /> : <NoSafeAction verdict={v} closest={focus} />}
      {focus?.details?.phase_moves && <PhasePlan moves={focus.details.phase_moves} />}
      {focus?.details?.export_limits && <Envelope limits={focus.details.export_limits} />}
      {focus?.details?.voltage && <VoltageCompare voltage={focus.details.voltage} label={focus.label} vmax={vmax} />}
      <CompareTable outcomes={result.outcomes} />
    </>
  )
}

function NoSafeAction({ verdict, closest }: { verdict: Verdict; closest?: Outcome }) {
  const t = useT()
  return (
    <section className="card no-safe" aria-labelledby="no-safe-title" data-numbers="no safe action">
      <h3 id="no-safe-title">{t('fixes.none_title')} <Prov kind="modeled" /></h3>
      <p>{t('fixes.none_body')}</p>
      {verdict.binding_limit && <p>{bindingText(t, verdict.binding_limit)}</p>}
      {closest && <p>{t('fixes.closest', { label: closest.label, steps: closest.unsafe_steps })}</p>}
      {verdict.still_needs && <p>{t('fixes.still_needs', { text: verdict.still_needs })}</p>}
    </section>
  )
}

function CompareTable({ outcomes }: { outcomes: Outcome[] }) {
  const t = useT()
  return (
    <section className="card" data-numbers="all options">
      <h3 id="compare-title">{t('fixes.compare_title')} <Prov kind="modeled" /></h3>
      <div className="table-scroll">
        <table className="data-table" aria-labelledby="compare-title">
          <thead>
            <tr>
              {(['col_option', 'col_safe', 'col_unsafe', 'col_curtailed', 'col_operations', 'col_margin', 'col_limit'] as const)
                .map((k) => <th key={k} scope="col">{t(`fixes.${k}`)}</th>)}
            </tr>
          </thead>
          <tbody>
            {outcomes.map((o) => (
              <tr key={o.id} className={o.safe ? 'row-safe' : 'row-unsafe'}>
                <th scope="row">{o.label}</th>
                <td>{t(o.safe ? 'fixes.yes' : 'fixes.no')}</td>
                <td>{o.unsafe_steps}</td>
                <td>{one(o.cost.curtailed_kwh)}</td>
                <td>{o.cost.operations}</td>
                <td>{one(o.cost.margin_v)}</td>
                <td>{o.binding_limit ? t(`limit.${o.binding_limit.type}` as StringKey) : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
