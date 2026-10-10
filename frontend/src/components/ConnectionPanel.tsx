import { useState, type CSSProperties } from 'react'
import { useV2 } from '../api/v2'
import type { ConnectionCheck } from '../api/v2types'
import { bindingText } from '../fixes'
import { one } from '../format'
import { useT } from '../i18n'
import Prov from './Prov'
import Status from './Status'

// Bounds of POST /connection-check (ConnectionRequest in backend/v2/routes_planning.py).
const KW = { min: 0.5, max: 50, step: 0.5 }
const COUNT = { min: 1, max: 50 }
const PHASES = ['', 'A', 'B', 'C'] as const

type Props = { node: number | null; network: string; rule: string; date: string | null }

const fill = (v: number, lo: number, hi: number) => ({ '--fill': `${((v - lo) / (hi - lo)) * 100}%` }) as CSSProperties

/** Connection check (E3): the place comes from the map; size, number of systems and phase from sliders and chips. */
export default function ConnectionPanel({ node, network, rule, date }: Props) {
  const t = useT()
  const [kw, setKw] = useState(3)
  const [count, setCount] = useState(1)
  const [phase, setPhase] = useState<(typeof PHASES)[number]>('')
  const [submitted, setSubmitted] = useState<string | null>(null)
  const result = useV2<ConnectionCheck>(submitted ? '/connection-check' : null, submitted ?? undefined)
  const submit = () => {
    if (node === null) return
    setSubmitted(JSON.stringify({ node, kw, count, phase: phase || null, network, rule, ...(date ? { date } : {}) }))
  }
  return (
    <div className="conn-panel" data-numbers="connection check">
      <form className="conn-form" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <p className="muted">{node === null ? t('plan.conn_pick') : t('plan.conn_picked', { node })}</p>
        <div className="slider-row">
          <div className="top"><label htmlFor="conn-kw">{t('plan.conn_kw')}</label><b>{one(kw)} kW</b></div>
          <input id="conn-kw" type="range" min={KW.min} max={KW.max} step={KW.step} value={kw} style={fill(kw, KW.min, KW.max)}
            onChange={(e) => setKw(Number(e.target.value))} />
        </div>
        <div className="slider-row">
          <div className="top"><label htmlFor="conn-count">{t('plan.conn_count')}</label><b>{count}</b></div>
          <input id="conn-count" type="range" min={COUNT.min} max={COUNT.max} step={1} value={count} style={fill(count, COUNT.min, COUNT.max)}
            onChange={(e) => setCount(Number(e.target.value))} />
        </div>
        <div className="row">
          <div className="rule-select">
            <span className="label" id="conn-phase-label">{t('plan.conn_phase')}</span>
            <div className="segmented" role="group" aria-labelledby="conn-phase-label">
              {PHASES.map((p) => (
                <button type="button" key={p || 'best'} className="seg" aria-pressed={phase === p} onClick={() => setPhase(p)}>
                  {p ? p : t('plan.conn_phase_best')}
                </button>
              ))}
            </div>
          </div>
          <button type="submit" className="btn btn-primary" disabled={node === null}>{t('plan.conn_run')}</button>
        </div>
      </form>
      {submitted && <Status state={result} />}
      {result.data && <Decision check={result.data} />}
    </div>
  )
}

export function Decision({ check }: { check: ConnectionCheck }) {
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
      <p className="muted">{t('plan.dec_evidence', { worse: ev.worsened_steps, base: ev.baseline_unsafe_steps, phases: perPhase })} <Prov kind="modeled" /></p>
      <p className="muted">{check.regulatory_status}</p>
    </section>
  )
}
