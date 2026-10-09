import { useState } from 'react'
import { useV2 } from '../api/v2'
import type { ConnectionCheck, Headroom } from '../api/v2types'
import { bindingText } from '../fixes'
import { useT, type StringKey } from '../i18n'
import { paramProblem } from '../whatif'
import Prov from './Prov'
import Status from './Status'

// Bounds of POST /connection-check (ConnectionRequest in backend/v2/routes_planning.py).
const KW = { type: 'number', exclusiveMinimum: 0, maximum: 50 } as const
const COUNT = { type: 'integer', minimum: 1, maximum: 50 } as const
const PHASES = ['A', 'B', 'C'] as const

type Props = { headroom: Headroom | null; network: string; rule: string; date: string | null }

/** Connection check (E3): approve, approve with conditions, or refuse new rooftop systems at a point of the street. */
export default function ConnectionForm({ headroom, network, rule, date }: Props) {
  const t = useT()
  const locations = Object.entries(headroom?.locations ?? {})
  const [where, setWhere] = useState('far')
  const [kw, setKw] = useState('3')
  const [count, setCount] = useState('1')
  const [phase, setPhase] = useState('')
  const [submitted, setSubmitted] = useState<string | null>(null)
  const result = useV2<ConnectionCheck>(submitted ? '/connection-check' : null, submitted ?? undefined)
  const node = headroom?.locations[where]?.node
  const valid = node !== undefined && paramProblem(KW, kw) === null && paramProblem(COUNT, count) === null

  const submit = () => {
    if (!valid) return
    setSubmitted(JSON.stringify({ node, kw: Number(kw), count: Number(count), phase: phase || null, network, rule,
      ...(date ? { date } : {}) }))
  }

  return (
    <section className="card" data-numbers="connection check">
      <h3>{t('plan.conn_title')} <Prov kind="modeled" /></h3>
      <form className="conn-form" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <div className="param">
          <label htmlFor="conn-where">{t('plan.conn_where')}</label>
          <select id="conn-where" value={where} onChange={(e) => setWhere(e.target.value)}>
            {locations.map(([id, loc]) => <option key={id} value={id}>{t(`plan.where_${id}` as StringKey, { node: loc.node })}</option>)}
          </select>
        </div>
        <div className="param">
          <label htmlFor="conn-kw">{t('plan.conn_kw')}</label>
          <input id="conn-kw" type="number" step="any" min={KW.exclusiveMinimum} max={KW.maximum} value={kw} onChange={(e) => setKw(e.target.value)}
            aria-invalid={paramProblem(KW, kw) !== null} />
          {paramProblem(KW, kw) && <span className="error" role="alert">{t('plan.conn_kw_error', { max: KW.maximum })}</span>}
        </div>
        <div className="param">
          <label htmlFor="conn-count">{t('plan.conn_count')}</label>
          <input id="conn-count" type="number" step={1} min={COUNT.minimum} max={COUNT.maximum} value={count}
            onChange={(e) => setCount(e.target.value)} aria-invalid={paramProblem(COUNT, count) !== null} />
          {paramProblem(COUNT, count) && (
            <span className="error" role="alert">{t('try.error_range', { min: COUNT.minimum, max: COUNT.maximum })}</span>
          )}
        </div>
        <div className="param">
          <label htmlFor="conn-phase">{t('plan.conn_phase')}</label>
          <select id="conn-phase" value={phase} onChange={(e) => setPhase(e.target.value)}>
            <option value="">{t('plan.conn_phase_best')}</option>
            {PHASES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <button type="submit" className="primary" disabled={!valid}>{t('plan.conn_run')}</button>
      </form>
      {submitted && <Status state={result} />}
      {result.data && <Decision check={result.data} />}
    </section>
  )
}

function Decision({ check }: { check: ConnectionCheck }) {
  const t = useT()
  const ev = check.evidence
  const perPhase = Object.entries(ev.per_phase_worsened_steps).map(([p, n]) => `${p}: ${n}`).join(' · ')
  return (
    <section className={`decision decision-${check.decision}`} aria-label={t('plan.decision')}>
      <p className="decision-line">
        {check.decision === 'approve' && t('plan.dec_approve', { kw: check.kw, count: check.count, phase: check.phase })}
        {check.decision === 'approve_with_conditions' && t('plan.dec_conditions', { conditions: check.conditions.join('; '), phase: check.phase })}
        {check.decision === 'refuse' && t('plan.dec_refuse', { kw: check.kw, count: check.count })}
      </p>
      {check.decision === 'refuse' && check.binding_limit && <p>{bindingText(t, check.binding_limit)}</p>}
      {check.decision === 'refuse' && check.largest_kw_that_passes !== undefined && (
        <p>{t('plan.dec_largest', { kw: check.largest_kw_that_passes })}</p>
      )}
      <p className="muted">{t('plan.dec_evidence', { worse: ev.worsened_steps, base: ev.baseline_unsafe_steps, phases: perPhase })}</p>
      <p className="muted">{check.regulatory_status}</p>
    </section>
  )
}
