import { useState } from 'react'
import { useV2 } from '../api/v2'
import type { Rule } from '../api/v2types'
import { AREAS, type Area } from '../app/areas'
import { NextStep } from '../components/Explainer'
import Status from '../components/Status'
import { useT, type StringKey } from '../i18n'

/** GET /surrogate (backend/v2/routes_surrogate.py). Every number comes from the evaluation files. */
type Screening = { unsafe_as_safe: number | null; truly_unsafe: number | null; false_rejections: number | null; truly_safe: number | null }
type Candidate = {
  kind: string; selected: boolean; node_level: boolean; voltage_mae_v: number | null; voltage_p99_v: number | null
  loading_mae_pts: number | null; loading_p99_pts: number | null; boundary_voltage_p99_v: number | null
  gates_passed: number; gates_total: number
}
type E1 = { runs: number; speedup_vs_solve_all: number; speedup_vs_cost_order: number; same_choice_as_solve_all: number
  false_rejections: number; overrules: number }
type E2 = { runs: number; speedup: number; skipped_candidates: number; candidates: number; false_rejections: number; same_best: number }
export type SurrogateStreet = {
  id: string; selected: string; selection_reason: string | null
  states: { train: number | null; test: number | null; boundary_test: number | null; out_of_range: number | null }
  guard_v: (number | null)[]; guard_loading_pts: (number | null)[]
  support: { taps: number[]; modes: string[]; battery_node: number; battery_kw: number[]; upstream_pu: number[] } | null
  candidates: Candidate[]
  gates: { name: string; value: number | null; target: number; passed: boolean }[]
  screening: { rule: string; split: string; guarded: Screening; point: Screening }[]
  out_of_range: { kind: string; states: number; unsupported: number }[]
  latency: { mode: string; batch: number; screen_ms_per_state: number | null; solver_ms_per_state: number | null }[]
  e1: E1 | null; e2: E2 | null
}
type Example = { source: string; type: string; caught_by_guard?: boolean
  predicted?: { v_max_v: number | null }; guarded?: { v_max_v: number | null }; solver?: { v_max_v: number | null } }
export type SurrogatePayload = {
  provenance: string; generated_at: string | null
  screener: { active: boolean; streets: string[]; reason: string }
  streets: SurrogateStreet[]
  disagreements: { counts: { source: string; type: string; rows: number }[]; examples: Example[] }
}

const NOT_BUILT = ['gnn', 'physics', 'gpu'] as const
const SOURCES: Record<string, string> = { 'held-out test split': 'heldout', 'controller-style run': 'e1', 'fix tournament': 'e2' }
const TYPES: Record<string, string> = { 'point prediction said safe': 'point', 'guarded screen said safe': 'guarded', 'screen said safe': 'screen',
  'safe at every step': 'screen' }
const num = (x: number | null | undefined, digits = 2) => (x === null || x === undefined ? '—' : String(Number(x.toFixed(digits))))

/** Addition 2: the power-flow surrogate. What it predicts, how often it would miss an unsafe state, what it refuses,
 *  and whether it is faster once the solver's check is included. It never decides on its own. */
export default function Surrogate({ go }: { go?: (area: Area) => void }) {
  const t = useT()
  const data = useV2<SurrogatePayload>('/surrogate')
  return (
    <div className="v2-page">
      <header className="page-hero">
        <span className="kicker">{t('journey.step', { n: AREAS.indexOf('surrogate') })} · {t('area.surrogate')}</span>
        <h2>{t('surrogate.page_title')}</h2>
        <p>{t('surrogate.page_intro')}</p>
      </header>
      <Status state={data} />
      {data.data && <SurrogateView d={data.data} />}
      <details className="more">
        <summary>{t('surrogate.not_built_title')}</summary>
        <ul>{NOT_BUILT.map((k) => <li key={k}>{t(`surrogate.not_built.${k}`)}</li>)}</ul>
      </details>
      <NextStep to="proof" go={go} />
    </div>
  )
}

function SurrogateView({ d }: { d: SurrogatePayload }) {
  const t = useT()
  const [chosen, setChosen] = useState<string | null>(null)
  const street = d.streets.find((s) => s.id === chosen) ?? d.streets[0]
  const streetName = (id: string) => t(`surrogate.street_name.${id}` as StringKey)
  return (
    <>
      <section className="card" aria-labelledby="sg-status">
        <h3 id="sg-status">{t('surrogate.status_title')} <span className="prov">{t('surrogate.simulated')}</span></h3>
        <p className={`gate-badge ${d.screener.active ? 'gate-pass' : 'gate-fail'}`} data-active={d.screener.active}>
          {d.screener.active ? t('surrogate.active', { streets: d.screener.streets.map(streetName).join(', ') })
            : t('surrogate.off', { reason: d.screener.reason })}
        </p>
        {d.streets.length > 1 && (
          <div className="segmented" role="group" aria-label={t('surrogate.street')}>
            {d.streets.map((s) => (
              <button key={s.id} className={`seg ${s.id === street?.id ? 'active' : ''}`} aria-pressed={s.id === street?.id}
                onClick={() => setChosen(s.id)}>{streetName(s.id)}</button>
            ))}
          </div>
        )}
        {d.generated_at && <p className="muted">{t('surrogate.provenance', { at: d.generated_at })}</p>}
      </section>
      {street && <StreetView s={street} />}
      <Disagreements d={d} />
    </>
  )
}

function StreetView({ s }: { s: SurrogateStreet }) {
  const t = useT()
  const rules = useV2<Rule[]>('/rules')
  const ruleLabel = (id: string) => rules.data?.find((r) => r.id === id)?.label ?? id
  const kind = (k: string) => t(`surrogate.kind.${k}` as StringKey)
  const mode = (m: string) => t(`surrogate.mode.${m}` as StringKey)
  return (
    <>
      <section className="stats" aria-label={t('surrogate.chosen')}>
        <div className="stat"><p>{t('surrogate.chosen')}</p><span className="value text">{kind(s.selected)}</span><p>{t('surrogate.chosen_why')}</p></div>
        <div className="stat"><p>{t('surrogate.states_train')}</p><span className="value">{num(s.states.train, 0)}</span></div>
        <div className="stat"><p>{t('surrogate.states_test')}</p><span className="value">{num(s.states.test, 0)}</span></div>
        <div className="stat"><p>{t('surrogate.states_boundary')}</p><span className="value">{num(s.states.boundary_test, 0)}</span></div>
        <div className="stat"><p>{t('surrogate.states_ood')}</p><span className="value">{num(s.states.out_of_range, 0)}</span></div>
        <div className="stat"><p>{t('surrogate.guard')}</p>
          <span className="value text">{t('surrogate.guard_value', { v: num(s.guard_v[0]), l: num(s.guard_loading_pts[0]) })}</span></div>
      </section>

      <section className="card" aria-labelledby="sg-accuracy">
        <h3 id="sg-accuracy">{t('surrogate.q_accuracy')}</h3>
        <p className="card-sub">{t('surrogate.q_accuracy_intro')}</p>
        <div className="table-scroll">
          <table className="data-table" aria-label={t('surrogate.q_accuracy')}>
            <thead><tr>{(['col_model', 'col_v_mae', 'col_v_p99', 'col_l_mae', 'col_l_p99', 'col_boundary', 'col_gates'] as const)
              .map((k) => <th key={k} scope="col">{t(`surrogate.${k}`)}</th>)}</tr></thead>
            <tbody>
              {s.candidates.map((c) => (
                <tr key={c.kind} data-selected={c.selected}>
                  <th scope="row">{kind(c.kind)} {c.selected && <span className="badge">{t('surrogate.selected')}</span>}
                    {!c.node_level && <span className="muted"> · {t('surrogate.extremes_only')}</span>}</th>
                  <td>{num(c.voltage_mae_v)}</td><td>{num(c.voltage_p99_v)}</td><td>{num(c.loading_mae_pts)}</td>
                  <td>{num(c.loading_p99_pts)}</td><td>{num(c.boundary_voltage_p99_v)}</td>
                  <td>{t('surrogate.of', { n: c.gates_passed, total: c.gates_total })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h3>{t('surrogate.gates_title')}</h3>
        <ul className="gate-summary">
          {s.gates.map((g) => (
            <li key={g.name} data-gate={g.name} data-passed={g.passed}>
              <span className={`gate-badge ${g.passed ? 'gate-pass' : 'gate-fail'}`}>{t(g.passed ? 'surrogate.passed' : 'surrogate.failed')}</span>{' '}
              {t(`surrogate.gate.${g.name}` as StringKey)}: {t('surrogate.gate_line', { value: num(g.value), target: num(g.target) })}
            </li>
          ))}
        </ul>
      </section>

      <section className="card" aria-labelledby="sg-misses">
        <h3 id="sg-misses">{t('surrogate.q_misses')}</h3>
        <p className="card-sub">{t('surrogate.q_misses_intro')}</p>
        <div className="table-scroll">
          <table className="data-table" aria-label={t('surrogate.q_misses')}>
            <thead><tr>{(['col_rule', 'col_split', 'col_missed', 'col_missed_point', 'col_false_rej'] as const)
              .map((k) => <th key={k} scope="col">{t(`surrogate.${k}`)}</th>)}</tr></thead>
            <tbody>
              {s.screening.map((r) => (
                <tr key={`${r.rule}-${r.split}`}>
                  <th scope="row">{ruleLabel(r.rule)}</th>
                  <td className="wrap">{t(`surrogate.split.${r.split}` as StringKey)}</td>
                  <td>{t('surrogate.of', { n: num(r.guarded.unsafe_as_safe, 0), total: num(r.guarded.truly_unsafe, 0) })}</td>
                  <td>{t('surrogate.of', { n: num(r.point.unsafe_as_safe, 0), total: num(r.point.truly_unsafe, 0) })}</td>
                  <td>{t('surrogate.of', { n: num(r.guarded.false_rejections, 0), total: num(r.guarded.truly_safe, 0) })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card" aria-labelledby="sg-limits">
        <h3 id="sg-limits">{t('surrogate.q_limits')}</h3>
        <p className="card-sub">{t('surrogate.q_limits_intro')}</p>
        {s.support && <p>{t('surrogate.support', { taps: s.support.taps.join(', '), modes: s.support.modes.map(mode).join(', '),
          bmin: num(s.support.battery_kw[0], 1), bmax: num(s.support.battery_kw[1], 1), node: s.support.battery_node,
          umin: num(s.support.upstream_pu[0], 3), umax: num(s.support.upstream_pu[1], 3) })}</p>}
        <div className="table-scroll">
          <table className="data-table" aria-label={t('surrogate.q_limits')}>
            <thead><tr><th scope="col">{t('surrogate.col_input')}</th><th scope="col">{t('surrogate.col_refused')}</th></tr></thead>
            <tbody>
              {s.out_of_range.map((o) => (
                <tr key={o.kind} data-all-refused={o.unsupported === o.states}>
                  <th scope="row">{t(`surrogate.ood.${o.kind}` as StringKey)}</th>
                  <td>{t('surrogate.of', { n: o.unsupported, total: o.states })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note" role="note">{t('surrogate.not_screened')}</p>
      </section>

      <section className="card" aria-labelledby="sg-speed">
        <h3 id="sg-speed">{t('surrogate.q_speed')}</h3>
        <p className="card-sub">{t('surrogate.q_speed_intro')}</p>
        <h3>{t('surrogate.e1_title')}</h3>
        <p data-section="e1">{s.e1 ? t('surrogate.e1_text', { runs: s.e1.runs, vs_all: num(s.e1.speedup_vs_solve_all), vs_order: num(s.e1.speedup_vs_cost_order),
          same: s.e1.same_choice_as_solve_all, fr: s.e1.false_rejections, over: s.e1.overrules }) : t('surrogate.not_run')}</p>
        <h3>{t('surrogate.e2_title')}</h3>
        <p data-section="e2">{s.e2 ? t('surrogate.e2_text', { runs: s.e2.runs, candidates: s.e2.candidates, skipped: s.e2.skipped_candidates,
          fr: s.e2.false_rejections, same: s.e2.same_best, speedup: num(s.e2.speedup) }) : t('surrogate.not_run')}</p>
        <div className="table-scroll">
          <table className="data-table" aria-label={t('surrogate.q_speed')}>
            <thead><tr>{(['col_mode', 'col_batch', 'col_screen', 'col_solver'] as const).map((k) => <th key={k} scope="col">{t(`surrogate.${k}`)}</th>)}</tr></thead>
            <tbody>
              {s.latency.map((l) => (
                <tr key={`${l.mode}-${l.batch}`}><th scope="row">{mode(l.mode)}</th><td>{l.batch}</td>
                  <td>{num(l.screen_ms_per_state, 4)}</td><td>{num(l.solver_ms_per_state, 4)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

function Disagreements({ d }: { d: SurrogatePayload }) {
  const t = useT()
  const source = (s: string) => (SOURCES[s] ? t(`surrogate.dis.source.${SOURCES[s]}` as StringKey) : s)
  const type = (s: string) => (TYPES[s] ? t(`surrogate.dis.type.${TYPES[s]}` as StringKey) : s)
  return (
    <section className="card" aria-labelledby="sg-dis">
      <h3 id="sg-dis">{t('surrogate.q_disagree')}</h3>
      <p className="card-sub">{t('surrogate.q_disagree_intro')}</p>
      {d.disagreements.counts.length === 0 ? <p>{t('surrogate.dis_none')}</p> : (
        <ul>{d.disagreements.counts.map((c) => (
          <li key={`${c.source}-${c.type}`}>{t('surrogate.dis_count', { rows: c.rows, type: type(c.type), source: source(c.source) })}</li>
        ))}</ul>
      )}
      <ul className="sg-examples">
        {d.disagreements.examples.map((e, i) => (
          <li key={i} className="note">
            <strong>{type(e.type)}</strong> · {source(e.source)}.{' '}
            {e.solver?.v_max_v !== undefined && t('surrogate.dis_case', { pred: num(e.predicted?.v_max_v ?? null, 1),
              guard: num(e.guarded?.v_max_v ?? null, 1), solver: num(e.solver?.v_max_v ?? null, 1) })}{' '}
            {e.caught_by_guard !== undefined && t(e.caught_by_guard ? 'surrogate.dis_caught' : 'surrogate.dis_missed')}{' '}
            {t('surrogate.dis_response')}
          </li>
        ))}
      </ul>
    </section>
  )
}
