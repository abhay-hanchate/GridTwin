import { useMemo, useState } from 'react'
import { useV2 } from '../api/v2'
import type { ControlRecord, ControlRun, ControlRuns } from '../api/v2types'
import type { Area } from '../app/areas'
import { NextStep } from '../components/Explainer'
import Prov from '../components/Prov'
import Status from '../components/Status'
import { one, pct } from '../format'
import { useT, type StringKey } from '../i18n'

const W = 960
const PAD = { l: 48, r: 12, t: 12, b: 26 }
const SAFE = 'verified_safe'

/** Addition 1: receding-horizon control of the battery, curtailment and switching, quarter hour by quarter hour.
 *  Every number comes from /control/runs (scripts/control_replay.py) or a replay job; observations are simulated. */
export default function Control({ go }: { go?: (area: Area) => void }) {
  const t = useT()
  const runs = useV2<ControlRuns>('/control/runs')
  const ids = runs.data ? Object.keys(runs.data.runs) : []
  const [picked, setPicked] = useState<string | null>(null)
  const id = picked ?? ids[0] ?? null
  const [custom, setCustom] = useState<string | null>(null)
  const run = useV2<ControlRun>(custom ? '/control/replay' : id ? `/control/runs/${encodeURIComponent(id)}` : null, custom ?? undefined)
  return (
    <div className="v2-page control-page">
      <header className="page-hero">
        <span className="kicker">{t('journey.step', { n: 5 })} · {t('area.control')}</span>
        <h2>{t('control.page_title')}</h2>
        <p>{t('control.page_intro')}</p>
      </header>
      <Status state={runs} />
      {runs.data && (
        <div className="segmented control-picker" role="group" aria-label={t('control.pick')}>
          {ids.map((k) => (
            <button key={k} className="seg" aria-pressed={k === id && !custom} onClick={() => { setPicked(k); setCustom(null) }}>
              {runs.data!.runs[k].title}
            </button>
          ))}
        </div>
      )}
      <Status state={run} />
      {run.data && <RunView run={run.data} />}
      {id && <Rerun fixture={id} onRun={setCustom} />}
      {runs.data?.near_limit && <NearLimit sweep={runs.data.near_limit} />}
      <p className="note" role="note">{t('control.honesty')}</p>
      <NextStep to="home" go={go} />
    </div>
  )
}

function RunView({ run }: { run: ControlRun }) {
  const t = useT()
  const s = run.summary
  return (
    <>
      <div className="kpis-v2" data-numbers="control comparison">
        <section className="card kpi">
          <div className="label">{t('control.kpi_unsafe')} <Prov kind="modeled" /></div>
          <div className="kpi-value">{t('control.of_steps', { n: s.unsafe_steps, total: s.steps })}</div>
          <p className="muted">{t('control.kpi_compare', { reactive: s.baseline_unsafe_steps, none: s.unsafe_steps_without_control })}</p>
        </section>
        <section className="card kpi">
          <div className="label">{t('control.kpi_soc')}</div>
          <div className="kpi-value">{pct(s.soc_min)} – {pct(s.soc_max)}</div>
          <p className="muted">{t('control.kpi_soc_sub', { min: pct(run.config.soc_min), max: pct(run.config.soc_max), final: pct(s.soc_final) })}</p>
        </section>
        <section className="card kpi">
          <div className="label">{t('control.kpi_actions')}</div>
          <div className="kpi-value">{t('control.kwh', { v: one(s.curtailed_kwh) })}</div>
          <p className="muted">{t('control.kpi_actions_sub', { thr: one(s.throughput_kwh), ops: s.operations_used, max: run.config.max_operations, fb: s.fallbacks })}</p>
        </section>
      </div>
      <section className="card" data-numbers="state of charge">
        <h3>{t('control.soc_title')} <Prov kind="modeled" /></h3>
        <p className="card-sub">{t('control.soc_sub')}</p>
        <SocChart run={run} />
      </section>
      <section className="card" data-numbers="actions">
        <h3>{t('control.actions_title')}</h3>
        <p className="card-sub">{t('control.actions_sub', { kw: one(run.config.battery_kw) })}</p>
        <ActionChart run={run} />
      </section>
      <section className="card" data-numbers="verification">
        <h3>{t('control.verify_title')}</h3>
        <p className="card-sub">{t('control.verify_sub')}</p>
        <VoltageChart run={run} />
      </section>
      <section className="card" aria-labelledby="periods-title">
        <h3 id="periods-title">{t('control.periods_title')}</h3>
        {s.infeasible_periods.length === 0
          ? <p className="muted">{t('control.periods_none')}</p>
          : <ul className="periods">{s.infeasible_periods.map((p) => (
            <li key={p.from}><b>{p.from === p.until ? p.from : `${p.from} – ${p.until}`}</b> · {p.statuses.join(', ')} · {p.first_reason}</li>
          ))}</ul>}
      </section>
      <Steps records={run.records} />
      <details className="more">
        <summary>{t('control.provenance_title')}</summary>
        <ul>{Object.entries(run.provenance).map(([k, v]) => <li key={k}><b>{k}</b>: {String(v)}</li>)}</ul>
        {run.switches.length > 0 && <ul>{run.switches.map((w) => <li key={w.id}><b>{w.id}</b>: {w.status}</li>)}</ul>}
        <p className="muted">{t('control.timing', { total: one(run.timing.total_s), p50: one(run.timing.step_p50_s), p95: one(run.timing.step_p95_s) })}</p>
      </details>
    </>
  )
}

function scale(n: number, h: number, lo: number, hi: number) {
  const x = (i: number) => PAD.l + (i * (W - PAD.l - PAD.r)) / Math.max(1, n - 1)
  const y = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo || 1)) * (h - PAD.t - PAD.b)
  return { x, y }
}

function Axis({ times, h, ticks, y, fmt }: { times: string[]; h: number; ticks: number[]; y: (v: number) => number; fmt: (v: number) => string }) {
  const n = times.length
  const every = Math.max(1, Math.round(n / 8))
  const { x } = scale(n, h, 0, 1)
  return (
    <g className="axis-g" aria-hidden="true">
      {ticks.map((v) => <g key={v}><line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="grid" /><text x={PAD.l - 6} y={y(v) + 4} textAnchor="end">{fmt(v)}</text></g>)}
      {times.map((tm, i) => (i % every === 0 ? <text key={tm} x={x(i)} y={h - 6} textAnchor="middle">{tm}</text> : null))}
    </g>
  )
}

function SocChart({ run }: { run: ControlRun }) {
  const t = useT()
  const h = 220
  const r = run.records
  const times = [r[0].time, ...r.map((x) => x.time)]
  const cap = run.config.battery_kwh
  const ours = [r[0].soc_before, ...r.map((x) => x.soc_after)]
  const base = run.baseline.energy_kwh.map((e) => e / cap)
  const { x, y } = scale(times.length, h, 0, 1)
  const path = (v: number[]) => v.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join('')
  return (
    <svg className="control-chart" viewBox={`0 0 ${W} ${h}`} role="img" aria-label={t('control.soc_label', { min: pct(Math.min(...ours)), max: pct(Math.max(...ours)) })}>
      <Axis times={times} h={h} ticks={[0, 0.25, 0.5, 0.75, 1]} y={y} fmt={(v) => pct(v)} />
      <rect x={PAD.l} width={W - PAD.l - PAD.r} y={y(run.config.soc_max)} height={y(run.config.soc_min) - y(run.config.soc_max)} className="soc-band" />
      <path d={path(base)} className="line baseline" />
      <path d={path(ours)} className="line ours" data-series="controller" />
      <g className="legend-g"><text x={PAD.l + 8} y={PAD.t + 14} className="ours-t">{t('control.legend_ours')}</text>
        <text x={PAD.l + 8} y={PAD.t + 30} className="base-t">{t('control.legend_reactive')}</text></g>
    </svg>
  )
}

function ActionChart({ run }: { run: ControlRun }) {
  const t = useT()
  const h = 220
  const r = run.records
  const kw = run.config.battery_kw
  const curtailedKw = r.map((x) => x.action.curtailed_kwh * 4)
  const top = Math.max(kw, ...curtailedKw, 1)
  const { x, y } = scale(r.length, h, -kw, top)
  const bw = Math.max(2, (W - PAD.l - PAD.r) / r.length - 3)
  return (
    <svg className="control-chart" viewBox={`0 0 ${W} ${h}`} role="img" aria-label={t('control.actions_label')}>
      <Axis times={r.map((v) => v.time)} h={h} ticks={[-kw, 0, kw]} y={y} fmt={(v) => one(v)} />
      {r.map((v, i) => {
        const p = v.action.battery_kw
        return <rect key={v.step} data-step={v.step} className={`bar ${p >= 0 ? 'charge' : 'discharge'}`} x={x(i) - bw / 2} width={bw}
          y={Math.min(y(0), y(p))} height={Math.abs(y(p) - y(0))}><title>{`${v.time} ${one(p)} kW`}</title></rect>
      })}
      <path className="line curtail" d={curtailedKw.map((c, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(c).toFixed(1)}`).join('')} />
      <g className="legend-g"><text x={PAD.l + 8} y={PAD.t + 14} className="charge-t">{t('control.legend_battery')}</text>
        <text x={PAD.l + 8} y={PAD.t + 30} className="curtail-t">{t('control.legend_curtail')}</text></g>
    </svg>
  )
}

function VoltageChart({ run }: { run: ControlRun }) {
  const t = useT()
  const h = 240
  const r = run.records
  const vals = r.flatMap((v) => [v.before.v_max_v, v.after.v_max_v, v.before.v_min_v, v.after.v_min_v]).filter((v): v is number => v !== null)
  const limits = run.limits_v
  const lo = Math.min(limits.min, ...vals) - 3
  const hi = Math.max(limits.max, ...vals) + 3
  const { x, y } = scale(r.length, h, lo, hi)
  const line = (get: (v: ControlRecord) => number | null) => r.map((v, i) => {
    const val = get(v)
    return val === null ? '' : `${i && get(r[i - 1]) !== null ? 'L' : 'M'}${x(i).toFixed(1)},${y(val).toFixed(1)}`
  }).join('')
  const bw = Math.max(2, (W - PAD.l - PAD.r) / r.length - 3)
  return (
    <svg className="control-chart" viewBox={`0 0 ${W} ${h}`} role="img" aria-label={t('control.verify_label', { safe: r.filter((v) => v.status === SAFE).length, total: r.length })}>
      <Axis times={r.map((v) => v.time)} h={h} ticks={[limits.min, limits.max]} y={y} fmt={(v) => one(v)} />
      {r.map((v, i) => <rect key={v.step} data-status={v.status} className={`status-tick ${v.status === SAFE ? 'ok' : 'bad'}`}
        x={x(i) - bw / 2} width={bw} y={h - PAD.b + 2} height={6}><title>{`${v.time} ${v.status}`}</title></rect>)}
      <path className="line before" d={line((v) => v.before.v_max_v)} />
      <path className="line after" d={line((v) => v.after.v_max_v)} />
      <path className="line before" d={line((v) => v.before.v_min_v)} />
      <path className="line after" d={line((v) => v.after.v_min_v)} />
      <g className="legend-g"><text x={PAD.l + 8} y={PAD.t + 14} className="after-t">{t('control.legend_after')}</text>
        <text x={PAD.l + 8} y={PAD.t + 30} className="before-t">{t('control.legend_before')}</text></g>
    </svg>
  )
}

function Steps({ records }: { records: ControlRecord[] }) {
  const t = useT()
  return (
    <details className="more control-steps">
      <summary>{t('control.steps_title', { n: records.length })}</summary>
      <div className="table-wrap">
        <table>
          <thead><tr>{(['time', 'status', 'battery', 'keep', 'soc', 'topology', 'reason'] as const).map((c) =>
            <th key={c}>{t(`control.col_${c}` as StringKey)}</th>)}</tr></thead>
          <tbody>{records.map((r) => (
            <tr key={r.step} data-step-row={r.step} className={r.status === SAFE ? '' : 'unsafe'}>
              <td>{r.time}</td><td>{r.status}</td><td>{`${one(r.action.battery_kw)} kW`}</td>
              <td>{r.action.keep.map((k) => pct(k)).join(' / ')}</td>
              <td>{`${pct(r.soc_before)} → ${pct(r.soc_after)}`}</td>
              <td>{r.topology_after}{r.topology_after !== r.topology_before ? ' *' : ''}</td>
              <td>{r.reason}{r.replan_triggers.length > 1 ? ` · ${r.replan_triggers.slice(1).join(', ')}` : ''}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </details>
  )
}

function Rerun({ fixture, onRun }: { fixture: string; onRun: (body: string) => void }) {
  const t = useT()
  const [soc, setSoc] = useState(50)
  const [curtail, setCurtail] = useState(true)
  const [switching, setSwitching] = useState(false)
  const body = useMemo(() => JSON.stringify({ fixture, soc_start: soc / 100, curtail, switching }), [fixture, soc, curtail, switching])
  return (
    <section className="card rerun" aria-labelledby="rerun-title">
      <h3 id="rerun-title">{t('control.rerun_title')}</h3>
      <p className="card-sub">{t('control.rerun_sub')}</p>
      <label className="field">{t('control.rerun_soc', { v: pct(soc / 100) })}
        <input type="range" min={10} max={90} step={5} value={soc} onChange={(e) => setSoc(Number(e.target.value))} />
      </label>
      <label className="check"><input type="checkbox" checked={curtail} onChange={(e) => setCurtail(e.target.checked)} /> {t('control.rerun_curtail')}</label>
      <label className="check"><input type="checkbox" checked={switching} onChange={(e) => setSwitching(e.target.checked)} /> {t('control.rerun_switching')}</label>
      <p><button className="btn btn-primary" onClick={() => onRun(body)}>{t('control.rerun_run')}</button></p>
    </section>
  )
}

function NearLimit({ sweep }: { sweep: NonNullable<ControlRuns['near_limit']> }) {
  const t = useT()
  return (
    <section className="card" data-numbers="near limit" aria-labelledby="near-title">
      <h3 id="near-title">{t('control.near_title')} <Prov kind="modeled" /></h3>
      <p className="card-sub">{t('control.near_sub', { time: sweep.time, limit: one(sweep.limit_v) })}</p>
      <div className="table-wrap"><table>
        <thead><tr><th>{t('control.near_col_sun')}</th><th>{t('control.near_col_v')}</th><th>{t('control.near_col_safe')}</th></tr></thead>
        <tbody>{sweep.rows.map((row) => (
          <tr key={row.solar_factor} className={row.safe ? '' : 'unsafe'}>
            <td>{pct(row.solar_factor)}</td><td>{`${one(row.v_max_v)} V`}</td><td>{t(row.safe ? 'control.yes' : 'control.no')}</td>
          </tr>
        ))}</tbody>
      </table></div>
    </section>
  )
}
