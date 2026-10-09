import { useState } from 'react'
import { useV2, v2Path } from '../api/v2'
import type { Risk, Rule } from '../api/v2types'
import Prov from '../components/Prov'
import RiskStrip from '../components/RiskStrip'
import Status from '../components/Status'
import Verdict from '../components/Verdict'
import { one, stepTime, volts } from '../format'
import { useT } from '../i18n'

// Watch and act levels of feature D1; the API states the ones it used and these are only the fallback.
const DEFAULT_THRESHOLDS = { watch: 0.2, act: 0.5 }
export const DEFAULT_NETWORK = 'benchmark_250'

export function RuleSelector({ rules, value, onChange }: { rules: Rule[]; value: string; onChange: (id: string) => void }) {
  const t = useT()
  const current = rules.find((r) => r.id === value)
  return (
    <div className="rule-select">
      <span className="label" id="rule-label">{t('home.rule')}</span>
      <div className="segmented" role="group" aria-labelledby="rule-label">
        {rules.map((r) => (
          <button key={r.id} aria-pressed={r.id === value} className={`seg ${r.id === value ? 'active' : ''}`}
            onClick={() => onChange(r.id)}>{r.label}</button>
        ))}
      </div>
      {current && <p className="muted">{t('home.rule_source', { source: current.source, verification: current.verification })}</p>}
    </div>
  )
}

export default function Home({ network = DEFAULT_NETWORK }: { network?: string }) {
  const t = useT()
  const [rule, setRule] = useState('up_2005')
  const rules = useV2<Rule[]>('/rules')
  const risk = useV2<Risk>(v2Path('/risk', { network, rule }))
  const band = rules.data?.find((r) => r.id === rule)

  return (
    <div className="v2-page">
      {rules.data ? <RuleSelector rules={rules.data} value={rule} onChange={setRule} /> : <Status state={rules} />}
      <Status state={risk} />
      {risk.data && <RiskView risk={risk.data} band={band} />}
      {risk.data && !risk.data.calibration?.reliable && <p className="note" role="note">{t('home.uncalibrated')}</p>}
    </div>
  )
}

function RiskView({ risk, band }: { risk: Risk; band?: Rule }) {
  const t = useT()
  const { watch, act } = risk.thresholds ?? DEFAULT_THRESHOLDS
  const times = risk.t ?? risk.p_unsafe.map((_, i) => stepTime(i))
  const hours = risk.expected_unsafe_hours
  const peak = risk.peak_voltage_v
  return (
    <>
      <Verdict risk={risk} times={times} act={act} />
      <section className="card" data-numbers="probability strip">
        <h3>{t('home.strip_title')} <Prov kind="modeled" /></h3>
        <RiskStrip p={risk.p_unsafe} times={times} watch={watch} act={act} />
      </section>
      <div className="kpis-v2">
        <section className="card kpi" data-numbers="expected unsafe hours">
          <div className="label">{t('home.hours')} <Prov kind="modeled" /></div>
          <div className="kpi-value">{t('home.hours_value', { value: one(hours.mean) })}</div>
          <p className="muted">{t('home.hours_range', { p10: one(hours.p10), p90: one(hours.p90) })}</p>
        </section>
        <section className="card kpi" data-numbers="peak voltage">
          <div className="label">{t('home.peak')} <Prov kind="modeled" /></div>
          <div className="kpi-value">{volts(peak.p50)} V</div>
          {band && (
            <p className="muted">{t('home.peak_range', {
              p10: volts(peak.p10), p90: volts(peak.p90), vmin: one(band.vmin_v), vmax: one(band.vmax_v),
            })}</p>
          )}
        </section>
      </div>
      <p className="muted inputs">{t('home.inputs', {
        solar: risk.provenance.solar ?? '', demand: risk.provenance.demand ?? '', voltage: risk.provenance.voltage ?? '',
      })}</p>
    </>
  )
}
