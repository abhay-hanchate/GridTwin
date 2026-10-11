import { CheckCircle2, CircleDashed, Download, FileText } from 'lucide-react'
import { useState } from 'react'
import { useV2, V2_BASE, v2Path } from '../api/v2'
import type { ControlRun, ControlRuns } from '../api/v2types'
import type { Area } from '../app/areas'
import { AREAS } from '../app/areas'
import { NextStep } from '../components/Explainer'
import { BarChart, GroupedBars, LineChart, LogPairs, StackedRows, type Tone } from '../components/evidence/Charts'
import Info from '../components/Info'
import Prov from '../components/Prov'
import Status from '../components/Status'
import { one } from '../format'
import { useT, type StringKey } from '../i18n'
import { ActionChart, NearLimit, SocChart, Steps, VoltageChart } from './Control'
import type { SurrogatePayload, SurrogateStreet } from './Surrogate'

/** Evidence: every item of the ENR-02 brief (base, Addition 1, Addition 2, required demonstrations and files), each
 *  with the chart, log or file that shows it. Every number comes from /control/runs, /surrogate or /evidence/files. */

type Item = { key: string; met: boolean; to: string }
const CHECKLIST: { group: string; items: Item[] }[] = [
  { group: 'base', items: [{ key: 'inputs', met: true, to: 'ev-a1' }, { key: 'checks', met: true, to: 'ev-a1' }] },
  { group: 'a1', items: [
    { key: 'horizon', met: true, to: 'ev-run' }, { key: 'soc', met: true, to: 'ev-soc' }, { key: 'limits', met: true, to: 'ev-verify' },
    { key: 'switch_curtail', met: true, to: 'ev-actions' }, { key: 'replan', met: true, to: 'ev-forecast' },
    { key: 'transitions', met: true, to: 'ev-log' }, { key: 'before_after', met: true, to: 'ev-verify' },
    { key: 'infeasible', met: true, to: 'ev-infeasible' }, { key: 'validated', met: true, to: 'ev-verify' },
  ] },
  { group: 'a2', items: [
    { key: 'generate', met: true, to: 'ev-splits' }, { key: 'train', met: true, to: 'ev-accuracy' },
    { key: 'candidate', met: false, to: 'ev-e2e' }, { key: 'final_solver', met: true, to: 'ev-dis' },
    { key: 'range', met: true, to: 'ev-range' }, { key: 'unseen', met: true, to: 'ev-splits' },
    { key: 'error', met: true, to: 'ev-accuracy' }, { key: 'misses', met: true, to: 'ev-misses' }, { key: 'time', met: false, to: 'ev-speed' },
  ] },
  { group: 'demo', items: [
    { key: 'd_forecast', met: true, to: 'ev-forecast' }, { key: 'd_battery', met: true, to: 'ev-soc' },
    { key: 'd_near', met: true, to: 'ev-near' }, { key: 'd_infeasible', met: true, to: 'ev-infeasible' }, { key: 'd_dis', met: true, to: 'ev-dis' },
  ] },
  { group: 'files', items: [{ key: 'files', met: true, to: 'ev-files' }] },
]

const BRIEF = 'ENR-02'
const MIN_HORIZON = 8                // the brief: plan over at least eight time steps
const RUN_ORDER = ['forecast_error', 'battery_saturation', 'depletion_infeasible', 'battery_only']
const go2 = (id: string) => () => document.getElementById(id)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
const kb = (n: number) => (n > 1e6 ? `${one(n / 1e6)} MB` : `${Math.max(1, Math.round(n / 1024))} kB`)

export default function Evidence({ go }: { go?: (area: Area) => void }) {
  const t = useT()
  const runs = useV2<ControlRuns>('/control/runs')
  const sur = useV2<SurrogatePayload>('/surrogate')
  const files = useV2<{ groups: { id: string; files: { path: string; what: string; bytes: number }[] }[] }>('/evidence/files')
  const all = CHECKLIST.flatMap((g) => g.items)
  const met = all.filter((i) => i.met).length

  return (
    <div className="v2-page evidence">
      <header className="page-hero">
        <span className="kicker">{t('journey.step', { n: AREAS.indexOf('evidence') })} · {t('area.evidence')}</span>
        <div className="hero-title"><h2>{t('ev.title', { brief: BRIEF })}</h2><Info>{t('ev.intro')}</Info></div>
      </header>

      <section className="card ev-score" aria-labelledby="ev-check-title">
        <div className="ev-score-head">
          <div>
            <h3 id="ev-check-title">{t('ev.check_title')}</h3>
            <p className="muted">{t('ev.check_sub')}</p>
          </div>
          <div className="ev-ring" style={{ ['--p' as string]: `${(met / all.length) * 100}%` }}>
            <b className="num">{met}</b><span>/ {all.length}</span>
          </div>
        </div>
        <div className="ev-groups">
          {CHECKLIST.map((g) => (
            <div key={g.group} className="ev-group">
              <h4>{t(`ev.g.${g.group}` as StringKey, { n: g.group === 'a2' ? 2 : 1 })}</h4>
              <ul>
                {g.items.map((it) => (
                  <li key={it.key} className={it.met ? 'met' : 'partial'}>
                    {it.met ? <CheckCircle2 size={17} aria-hidden="true" /> : <CircleDashed size={17} aria-hidden="true" />}
                    <button type="button" onClick={go2(it.to)}>{t(`ev.i.${it.key}` as StringKey, { n: MIN_HORIZON })}</button>
                    {!it.met && <span className="ev-tag">{t('ev.partial')}</span>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <h2 className="ev-section" id="ev-a1">{t('ev.a1_title', { n: 1 })}</h2>
      <Status state={runs} />
      {runs.data && <ControlEvidence runs={runs.data} />}

      <h2 className="ev-section" id="ev-a2">{t('ev.a2_title', { n: 2 })}</h2>
      <Status state={sur} />
      {sur.data && <SurrogateEvidence d={sur.data} />}

      <section className="card" id="ev-files" aria-labelledby="ev-files-title">
        <div className="card-head"><h3 id="ev-files-title">{t('ev.files_title')}</h3><Info>{t('ev.files_sub')}</Info></div>
        <Status state={files} />
        {files.data && (
          <div className="ev-files">
            {files.data.groups.map((g) => (
              <div key={g.id} className="ev-file-group">
                <h4>{t(`ev.f.${g.id}` as StringKey)} <span className="muted">{g.files.length}</span></h4>
                <ul>
                  {g.files.map((f) => (
                    <li key={f.path}>
                      <FileText size={15} aria-hidden="true" />
                      <a href={`${V2_BASE}${v2Path('/evidence/file', { path: f.path })}`} download>{f.path}</a>
                      <span className="muted">{f.what}</span>
                      <span className="num muted">{kb(f.bytes)}</span>
                      <Download size={14} aria-hidden="true" className="ev-dl" />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      <NextStep to="home" go={go} />
    </div>
  )
}

/* ---- Addition 1 -------------------------------------------------------------------------------------------- */

function ControlEvidence({ runs }: { runs: ControlRuns }) {
  const t = useT()
  const ids = RUN_ORDER.filter((id) => id in runs.runs).concat(Object.keys(runs.runs).filter((id) => !RUN_ORDER.includes(id)))
  const [id, setId] = useState(ids[0])
  const run = useV2<ControlRun>(id ? `/control/runs/${encodeURIComponent(id)}` : null)
  const s = runs.runs[id]?.summary
  return (
    <>
      <section className="card" id="ev-run" aria-labelledby="ev-run-title">
        <div className="card-head"><h3 id="ev-run-title">{t('ev.runs_title')}</h3><Prov kind="modeled" /><Info>{t('ev.runs_sub')}</Info></div>
        <div className="segmented ev-runs" role="group" aria-label={t('ev.runs_title')}>
          {ids.map((r) => <button key={r} className="seg" aria-pressed={r === id} onClick={() => setId(r)}>{t(`ev.run.${r}` as StringKey)}</button>)}
        </div>
        {s && (
          <div className="ev-kpis">
            <Kpi label={t('ev.k_without')} value={`${s.unsafe_steps_without_control}`} sub={`/ ${s.steps}`} tone="coral" />
            <Kpi label={t('ev.k_reactive')} value={`${s.baseline_unsafe_steps}`} sub={`/ ${s.steps}`} tone="sun" />
            <Kpi label={t('ev.k_controller')} value={`${s.unsafe_steps}`} sub={`/ ${s.steps}`} tone="leaf" />
            <Kpi label={t('ev.k_horizon')} value={`${s.horizon}`} sub={t('ev.k_steps')} tone="deep" />
            <Kpi label={t('ev.k_replans')} value={`${s.replans}`} sub={t('ev.k_fallbacks', { n: s.fallbacks })} tone="deep" />
            <Kpi label={t('ev.k_soc')} value={`${Math.round(s.soc_min * 100)}–${Math.round(s.soc_max * 100)}%`} sub={t('ev.k_final', { pct: Math.round(s.soc_final * 100) })} tone="deep" />
          </div>
        )}
      </section>
      <Status state={run} />
      {run.data && <RunEvidence run={run.data} />}
      {runs.near_limit && (
        <section className="card" id="ev-near" aria-labelledby="ev-near-title">
          <div className="card-head"><h3 id="ev-near-title">{t('ev.near_title')}</h3><Prov kind="modeled" /><Info>{t('ev.near_sub', { lo: `${Math.round(runs.near_limit.rows[0].solar_factor * 100)}%`, hi: `${Math.round(runs.near_limit.rows[runs.near_limit.rows.length - 1].solar_factor * 100)}%` })}</Info></div>
          <BarChart label={t('ev.near_title')} labels={runs.near_limit.rows.map((r) => `${Math.round(r.solar_factor * 100)}%`)}
            values={runs.near_limit.rows.map((r) => r.v_max_v)} tones={runs.near_limit.rows.map((r) => (r.safe ? 'leaf' : 'coral') as Tone)}
            refs={[{ y: runs.near_limit.limit_v, label: `${t('ev.limit')} ${one(runs.near_limit.limit_v)} V`, tone: 'coral' }]}
            valueFmt={(v) => `${one(v)} V`} yFmt={(v) => `${v}`} />
          <NearLimit sweep={runs.near_limit} />
        </section>
      )}
    </>
  )
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: Tone }) {
  return <div className={`ev-kpi tone-${tone}`}><span className="label">{label}</span><b className="num">{value}</b><small>{sub}</small></div>
}

function RunEvidence({ run }: { run: ControlRun }) {
  const t = useT()
  const r = run.records
  const times = r.map((x) => x.time)
  const f = (k: 'pv_per_kwp' | 'load_kw' | 'upstream_pu') => ({
    fc: r.map((x) => x.forecast?.forecast?.[k] ?? null), ob: r.map((x) => x.forecast?.observed?.[k] ?? null),
  })
  const pv = f('pv_per_kwp')
  const load = f('load_kw')
  const up = f('upstream_pu')
  const safe = r.filter((x) => x.status === 'verified_safe').length
  return (
    <>
      <section className="card" id="ev-forecast" aria-labelledby="ev-fc-title">
        <div className="card-head"><h3 id="ev-fc-title">{t('ev.fc_title')}</h3><Prov kind="modeled" /><Info>{t('ev.fc_sub')}</Info></div>
        <div className="ev-split">
          <LineChart label={t('ev.fc_solar')} title={t('ev.fc_solar')} width={560} x={times} height={250} yFmt={(v) => one(v)}
            series={[{ id: 'f', label: t('ev.forecast'), values: pv.fc, tone: 'ink', dashed: true },
              { id: 'o', label: t('ev.observed'), values: pv.ob, tone: 'sun', area: true }]} />
          <LineChart label={t('ev.fc_load')} title={t('ev.fc_load')} width={560} x={times} height={250} yFmt={(v) => one(v)}
            series={[{ id: 'f', label: t('ev.forecast'), values: load.fc, tone: 'ink', dashed: true },
              { id: 'o', label: t('ev.observed'), values: load.ob, tone: 'steel', area: true }]} />
        </div>
        <LineChart label={t('ev.fc_grid')} title={t('ev.fc_grid')} x={times} height={230} yFmt={(v) => `${Math.round(v * 230)}`}
          series={[{ id: 'f', label: t('ev.forecast_v'), values: up.fc, tone: 'ink', dashed: true },
            { id: 'o', label: t('ev.observed_v'), values: up.ob, tone: 'deep', area: true }]} />
      </section>

      <section className="card" id="ev-soc" aria-labelledby="ev-soc-title">
        <div className="card-head"><h3 id="ev-soc-title">{t('ev.soc_title')}</h3><Prov kind="modeled" /><Info>{t('ev.soc_sub')}</Info></div>
        <SocChart run={run} />
      </section>

      <section className="card" id="ev-actions" aria-labelledby="ev-act-title">
        <div className="card-head"><h3 id="ev-act-title">{t('ev.act_title')}</h3><Info>{t('ev.act_sub')}</Info></div>
        <ActionChart run={run} />
        <div className="ev-chips">
          <span className="chip">{t('ev.curtailed', { kwh: one(run.summary.curtailed_kwh) })}</span>
          <span className="chip">{t('ev.throughput', { kwh: one(run.summary.throughput_kwh), base: one(run.summary.baseline_throughput_kwh) })}</span>
          <span className="chip">{t('ev.switch_ops', { n: run.summary.operations_used, max: run.config.max_operations })}</span>
        </div>
      </section>

      <section className="card" id="ev-verify" aria-labelledby="ev-ver-title">
        <div className="card-head"><h3 id="ev-ver-title">{t('ev.ver_title')}</h3><Info>{t('ev.ver_sub')}</Info></div>
        <VoltageChart run={run} />
        <div className="ev-status-strip" role="img" aria-label={t('ev.ver_strip', { safe, total: r.length })}>
          {r.map((x) => <span key={x.step} className={x.status === 'verified_safe' ? 'ok' : 'bad'} title={`${x.time} ${x.status}`} />)}
        </div>
        <p className="muted">{t('ev.ver_strip', { safe, total: r.length })}</p>
      </section>

      <section className="card" id="ev-infeasible" aria-labelledby="ev-inf-title">
        <div className="card-head"><h3 id="ev-inf-title">{t('ev.inf_title')}</h3></div>
        {run.summary.infeasible_periods.length === 0
          ? <p className="ev-none">{t('ev.inf_none')}</p>
          : <ul className="ev-periods">{run.summary.infeasible_periods.map((p) => (
            <li key={p.from}><b className="num">{p.from}–{p.until}</b><span className="chip act">{p.statuses.join(', ')}</span><span>{p.first_reason}</span></li>))}</ul>}
      </section>

      <section className="card" id="ev-log" aria-labelledby="ev-log-title">
        <div className="card-head"><h3 id="ev-log-title">{t('ev.log_title')}</h3><Info>{t('ev.log_sub')}</Info></div>
        <Steps records={r} />
        <details className="fineprint">
          <summary>{t('ev.config')}</summary>
          <table className="data-table ev-config"><tbody>
            {Object.entries(run.config).filter(([, v]) => typeof v !== 'object' || v === null).map(([k, v]) => (
              <tr key={k}><th scope="row">{k}</th><td>{String(v)}</td></tr>))}
            {Object.entries(run.provenance).map(([k, v]) => <tr key={`p-${k}`}><th scope="row">{k}</th><td>{String(v)}</td></tr>)}
          </tbody></table>
        </details>
      </section>
    </>
  )
}

/* ---- Addition 2 -------------------------------------------------------------------------------------------- */

const SHORT: Record<string, string> = { benchmark_250: 'Benchmark', rural_long_100: 'Rural long', rural_weak_63: 'Rural weak',
  urban_short_160: 'Urban', suburban_100: 'Suburban' }
const name = (id: string) => SHORT[id] ?? id
const LATENCY_BATCH = 128                       // states per call in the latency table that every street reports
const x2 = (v: number) => String(Math.round(v * 100) / 100)

function SurrogateEvidence({ d }: { d: SurrogatePayload }) {
  const t = useT()
  const streets = d.streets
  const [sid, setSid] = useState(streets[0]?.id)
  const s = streets.find((x) => x.id === sid) ?? streets[0]
  const cand = (k: string) => streets.map((x) => (x.candidates as unknown as { kind: string; voltage_mae_v: number | null }[])
    .find((c) => c.kind === k)?.voltage_mae_v ?? null)
  return (
    <>
      <section className="card" id="ev-splits" aria-labelledby="ev-spl-title">
        <div className="card-head"><h3 id="ev-spl-title">{t('ev.spl_title')}</h3><Prov kind="modeled" /><Info>{t('ev.spl_sub')}</Info></div>
        <StackedRows label={t('ev.spl_title')} rows={streets.map((x) => ({ label: name(x.id), values: [
          x.states.train ?? 0, (x.states as Record<string, number | null>).tune ?? 0, (x.states as Record<string, number | null>).calibrate ?? 0,
          x.states.test ?? 0, x.states.out_of_range ?? 0] }))}
          parts={[{ label: t('ev.train'), tone: 'deep' }, { label: t('ev.tune'), tone: 'leaf' }, { label: t('ev.calibrate'), tone: 'mint' },
            { label: t('ev.test'), tone: 'sun' }, { label: t('ev.oor'), tone: 'coral' }]} />
      </section>

      <section className="card" id="ev-accuracy" aria-labelledby="ev-acc-title">
        <div className="card-head"><h3 id="ev-acc-title">{t('ev.acc_title')}</h3><Prov kind="modeled" /><Info>{t('ev.acc_sub')}</Info></div>
        <GroupedBars label={t('ev.acc_title')} groups={streets.map((x) => name(x.id))} yFmt={(v) => `${v} V`} valueFmt={(v) => `${v} V`}
          series={[{ label: 'Ridge', tone: 'mint', values: cand('ridge') }, { label: 'LightGBM', tone: 'leaf', values: cand('lgbm') },
            { label: 'MLP', tone: 'deep', values: cand('mlp') }]}
          refs={[{ y: 0.5, label: t('ev.target', { v: '0.5 V' }), tone: 'coral' }]} />
        <p className="muted">{t('ev.selected')} {streets.map((x) => `${name(x.id)}: ${x.selected.toUpperCase()}`).join(' · ')}</p>
      </section>

      <section className="card" id="ev-misses" aria-labelledby="ev-mis-title">
        <div className="card-head"><h3 id="ev-mis-title">{t('ev.mis_title')}</h3><Prov kind="modeled" /><Info>{t('ev.mis_sub', { pct: '95%' })}</Info></div>
        <div className="ev-table-wrap"><table className="data-table">
          <thead><tr><th scope="col">{t('ev.street')}</th><th scope="col">{t('ev.rule')}</th><th scope="col">{t('ev.mis_unsafe_safe')}</th>
            <th scope="col">{t('ev.mis_bound', { pct: '95%' })}</th><th scope="col">{t('ev.mis_false_rej')}</th></tr></thead>
          <tbody>{streets.flatMap((x) => x.screening.filter((sc) => sc.split === 'base').map((sc) => {
            const g = sc.guarded as unknown as Record<string, number>
            return (
              <tr key={`${x.id}-${sc.rule}`} className={g.unsafe_as_safe > 0 ? 'row-warn' : undefined}>
                <th scope="row">{name(x.id)}</th><td>{sc.rule === 'pm10' ? '±10%' : '±6%'}</td>
                <td>{g.unsafe_as_safe} / {g.truly_unsafe?.toLocaleString('en-IN')}</td>
                <td>{one(g.miss_upper95_per_10k ?? g.miss_rate_upper95 * 1e4)} / 10k</td>
                <td>{Math.round((g.false_rejection_rate ?? 0) * 100)}%</td>
              </tr>
            )
          }))}</tbody>
        </table></div>
        <h4 className="ev-sub">{t('ev.rounds_title', { rule: '±6%' })}</h4>
        <GroupedBars label={t('ev.rounds_title', { rule: '±6%' })} groups={['1', '2', '3', '4'].map((n) => `${t('ev.round')} ${n}`)}
          series={streets.filter((x) => x.rounds.some((r) => r.round < 4)).map((x, i) => ({
            label: name(x.id), tone: (['deep', 'leaf', 'sun', 'steel', 'mint'] as Tone[])[i % 5],
            values: [1, 2, 3, 4].map((n) => x.rounds.find((r) => r.round === n && r.rule === 'up_2005')?.unsafe_as_safe ?? null) }))}
          valueFmt={(v) => String(v)} />
      </section>

      <section className="card" id="ev-range" aria-labelledby="ev-rng-title">
        <div className="card-head"><h3 id="ev-rng-title">{t('ev.rng_title')}</h3><Info>{t('ev.rng_sub')}</Info></div>
        <div className="segmented" role="group" aria-label={t('ev.street')}>
          {streets.map((x) => <button key={x.id} className="seg" aria-pressed={x.id === s.id} onClick={() => setSid(x.id)}>{name(x.id)}</button>)}
        </div>
        <SupportTable s={s} />
        <h4 className="ev-sub">{t('ev.oor_title')}</h4>
        <BarChart label={t('ev.oor_title')} labels={s.out_of_range.map((o) => o.kind.replace(/_/g, ' '))}
          values={s.out_of_range.map((o) => Math.round((o.unsupported / o.states) * 100))}
          tones={s.out_of_range.map((o) => (o.unsupported === o.states ? 'leaf' : 'sun') as Tone)} yFmt={(v) => `${v}%`} valueFmt={(v) => `${v}%`}
          refs={[{ y: 100, label: t('ev.all_refused'), tone: 'deep' }]} height={230} />
      </section>

      <section className="card" id="ev-speed" aria-labelledby="ev-spd-title">
        <div className="card-head"><h3 id="ev-spd-title">{t('ev.spd_title')}</h3><Info>{t('ev.spd_sub')}</Info></div>
        <LogPairs label={t('ev.spd_title')} unit="ms"
          rows={streets.flatMap((x) => x.latency.filter((l) => l.batch === LATENCY_BATCH && l.screen_ms_per_state && l.solver_ms_per_state)
            .map((l) => ({ label: `${name(x.id)} · ${l.mode === 'volt_var' ? 'Volt/VAR' : 'fixed PF'}`, a: l.screen_ms_per_state!, b: l.solver_ms_per_state! })))
            .sort((p, q) => q.b / q.a - p.b / p.a)}
          a={{ label: t('ev.screen'), tone: 'leaf' }} b={{ label: t('ev.solver'), tone: 'coral' }} />
        <div id="ev-e2e" className="ev-e2e">
          {s.e1 && <div className="ev-kpi tone-deep"><span className="label">{t('ev.e1')}</span>
            <b className="num">{x2(s.e1.speedup_vs_cost_order)}×</b><small>{t('ev.same_choice', { n: s.e1.same_choice_as_solve_all, of: s.e1.runs })}</small></div>}
          {s.e2 && <div className="ev-kpi tone-deep"><span className="label">{t('ev.e2')}</span>
            <b className="num">{x2(s.e2.speedup)}×</b><small>{t('ev.same_best', { n: s.e2.same_best, of: s.e2.runs, skipped: s.e2.skipped_candidates })}</small></div>}
          <p className="note" role="note">{t('ev.e2e_note')}</p>
        </div>
      </section>

      <section className="card" id="ev-dis" aria-labelledby="ev-dis-title">
        <div className="card-head"><h3 id="ev-dis-title">{t('ev.dis_title')}</h3><Info>{t('ev.dis_sub')}</Info></div>
        <div className="ev-chips">{d.disagreements.counts.map((c) => <span key={c.type} className="chip">{c.type}: <b>{c.rows}</b></span>)}</div>
        <div className="ev-table-wrap"><table className="data-table">
          <thead><tr><th scope="col">{t('ev.street')}</th><th scope="col">{t('ev.dis_type')}</th><th scope="col">{t('ev.dis_pred')}</th>
            <th scope="col">{t('ev.dis_guard')}</th><th scope="col">{t('ev.dis_solver')}</th><th scope="col">{t('ev.dis_resp')}</th></tr></thead>
          <tbody>{d.disagreements.examples.slice(0, 12).map((e, i) => {
            const x = e as unknown as { street?: string; type: string; predicted?: { v_max_v: number | null }; guarded?: { v_max_v: number | null }
              solver?: { v_max_v: number | null }; solver_response?: string }
            return (
              <tr key={i}><th scope="row">{name(x.street ?? '')}</th><td>{x.type}</td><td>{x.predicted?.v_max_v ?? '—'} V</td>
                <td>{x.guarded?.v_max_v ?? '—'} V</td><td><b>{x.solver?.v_max_v ?? '—'} V</b></td><td>{x.solver_response ?? ''}</td></tr>
            )
          })}</tbody>
        </table></div>
      </section>
    </>
  )
}

function SupportTable({ s }: { s: SurrogateStreet }) {
  const t = useT()
  const sup = s.support as (SurrogateStreet['support'] & { novelty?: { threshold: number }; not_screened?: string[] }) | null
  if (!sup) return <p className="muted">{t('ev.no_support')}</p>
  const rows: [string, string][] = [
    [t('ev.r_taps'), sup.taps.join(', ')], [t('ev.r_modes'), sup.modes.join(', ').replace(/_/g, ' ')],
    [t('ev.r_battery'), `${Math.round(Math.abs(sup.battery_kw[0]))} kW · nodes ${sup.battery_nodes.join(', ')}`],
    [t('ev.r_grid'), `${Math.round(sup.upstream_pu[0] * 230)}–${Math.round(sup.upstream_pu[1] * 230)} V`],
    [t('ev.r_layouts'), String(sup.line_layouts ?? '—')], [t('ev.r_novelty'), sup.novelty ? one(sup.novelty.threshold) : '—'],
    [t('ev.r_fallback'), (sup.not_screened ?? []).join('; ') || t('ev.r_solver')],
  ]
  return (
    <div className="ev-support">
      {rows.map(([k, v]) => <div key={k}><span className="label">{k}</span><b>{v}</b></div>)}
    </div>
  )
}
