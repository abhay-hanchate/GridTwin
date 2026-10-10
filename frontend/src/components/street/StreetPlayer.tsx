import { useEffect, useMemo, useState } from 'react'
import { useV2, v2Path } from '../../api/v2'
import type { Street, StreetRun } from '../../api/v2types'
import { one, volts } from '../../format'
import { useT, type StringKey } from '../../i18n'
import Prov from '../Prov'
import Status from '../Status'
import VoltageCompare from '../VoltageCompare'
import { PHASES, balance, depth, homeFlows, phaseKw } from './balance'
import DayStrip from './DayStrip'
import HomeCard from './HomeCard'
import Num from './Num'
import StreetDayCharts from './StreetDayCharts'
import StreetView, { type HomeNow } from './StreetView'

const SPEEDS = [0.5, 1, 2] as const
const STEPS_PER_SECOND = 4                       // at 1x a day plays in 24 seconds

type Props = {
  network: string
  rule: string
  date: string | null
  fix?: string
  fixLabel?: string
  startStep?: number
  compact?: boolean
  presentation?: 'standard' | 'forecast' | 'compare'
}

/** The street through the design day: the transformer, its three phases and every home on them, quarter hour by
 *  quarter hour, with which way the power flows and what it does to each home's voltage. Loads /street. */
export default function StreetPlayer({ network, rule, date, fix = 'none', fixLabel, startStep, compact, presentation = 'standard' }: Props) {
  const street = useV2<Street>(date ? v2Path('/street', { network, rule, date, fix }) : null)
  if (!street.data) return <Status state={street} />
  return <Player key={`${street.data.date}-${street.data.rule}-${street.data.fix}`} s={fixLabel ? { ...street.data, fix_label: fixLabel } : street.data}
    startStep={startStep} compact={compact} presentation={presentation} />
}

function dayPart(time: string): StringKey {
  const h = Number(time.slice(0, 2))
  if (h < 6 || h >= 20) return 'player.night'
  if (h < 10) return 'player.morning'
  if (h < 16) return 'player.midday'
  return 'player.evening'
}

const finite = (v: number | null): v is number => v !== null && Number.isFinite(v)

function Player({ s, startStep, compact, presentation }: { s: Street; startStep?: number; compact?: boolean; presentation: NonNullable<Props['presentation']> }) {
  if (presentation === 'compare' && s.after) return <ComparePlayer s={s} startStep={startStep} />
  if (presentation === 'forecast') return <ForecastPlayer s={s} startStep={startStep} />
  return <StandardPlayer s={s} startStep={startStep} compact={compact} />
}

function usePlayback(n: number, initial: number) {
  const [step, setStep] = useState(initial)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1)
  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setStep((k) => (k + 1) % n), 1000 / (STEPS_PER_SECOND * speed))
    return () => clearInterval(id)
  }, [playing, speed, n])
  return { step, setStep, playing, setPlaying, speed, setSpeed }
}

function PlaybackControls({ s, run, scale, state }: {
  s: Street
  run: StreetRun
  scale: number
  state: ReturnType<typeof usePlayback>
}) {
  const t = useT()
  const { step, setStep, playing, setPlaying, speed, setSpeed } = state
  return (
    <div className="player-top">
      <button className="play-btn" onClick={() => setPlaying((p) => !p)} aria-label={t(playing ? 'player.pause' : 'player.play')}>
        {playing
          ? <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="4" y="3" width="4" height="14" rx="1" fill="currentColor" /><rect x="12" y="3" width="4" height="14" rx="1" fill="currentColor" /></svg>
          : <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3 L17 10 L5 17 Z" fill="currentColor" /></svg>}
      </button>
      <div className="clock" aria-live="off"><span className="time">{s.t[step]}</span><span className="phase-of-day">{t(dayPart(s.t[step]))}</span></div>
      <div className="scrub">
        <DayStrip t={s.t} grid={run.trafo_kw} solar={run.solar_kw} unsafe={run.unsafe} maxKw={scale} step={step}
          onStep={(k) => { setStep(k); setPlaying(false) }} />
      </div>
      <div className="speed segmented" role="group" aria-label={t('player.speed')}>
        {SPEEDS.map((v) => <button key={v} className="seg" aria-pressed={speed === v} onClick={() => setSpeed(v)}>{`${v}×`}</button>)}
      </div>
    </div>
  )
}

function mapScale(s: Street, runs: StreetRun[]) {
  const flows = runs.map((r) => homeFlows(s, r))
  return {
    flows,
    scale: {
      grid: Math.max(1, ...runs.flatMap((r) => [...r.trafo_kw.map(Math.abs), ...r.solar_kw])),
      phase: Math.max(1, ...runs.flatMap((r) => r.trafo_kw.map((_, k) => Math.max(...phaseKw(s, r, k).map(Math.abs))))),
      home: Math.max(0.5, ...flows.flatMap((f) => f.net.flat().map(Math.abs))),
    },
  }
}

function SimMap({ s, run, flows, scale, step, heading, tone }: {
  s: Street
  run: StreetRun
  flows: ReturnType<typeof homeFlows>
  scale: { grid: number; phase: number; home: number }
  step: number
  heading: string
  tone: 'before' | 'after'
}) {
  const t = useT()
  const [home, setHome] = useState<number | null>(null)
  const dist = useMemo(() => { const d = depth(s); return s.homes.map((h) => d.get(h.node) ?? 0) }, [s])
  const kwp = useMemo(() => s.homes.map((h) => h.kwp), [s])
  const b = balance(s, run, step)
  const ph = phaseKw(s, run, step)
  const vs = run.home_v[step]
  const now: HomeNow[] = vs.map((v, i) => ({ v, solar: flows.solar[step][i], demand: flows.demand[step][i], net: flows.net[step][i] }))
  const solved = vs.filter(finite)
  const vmax = solved.length ? Math.max(...solved) : NaN
  const outside = (v: number | null) => finite(v) && (v > s.limits_v.max || v < s.limits_v.min)
  const over = vs.filter(outside).length
  return (
    <section className={`sim-pane sim-${tone}`} aria-label={heading}>
      <header><span>{heading}</span><strong className={over ? 'act' : 'ok'}>{over ? t('compare.outside', { count: over }) : t('compare.safe')}</strong></header>
      <StreetView phase={run.home_phase} dist={dist} kwp={kwp} now={now} phaseKw={ph} grid={b.grid} scale={scale}
        limits={s.limits_v} trafoKva={s.trafo_kva} loadingPct={run.trafo_loading_pct[step]} selected={home} onHome={setHome}
        label={t('player.map_label', { time: s.t[step], over, total: s.homes.length, vmax: Number.isFinite(vmax) ? one(vmax) : '—' })} />
      <div className={`sim-result ${over ? 'act' : 'ok'}`}><span>{t('compare.highest')}</span><b>{Number.isFinite(vmax) ? `${volts(vmax)} V` : '—'}</b></div>
      {home !== null && <HomeCard home={home} phase={run.home_phase[home]} kwp={kwp[home]} now={now[home]} shared={flows.shared[home]}
        limits={s.limits_v} onClose={() => setHome(null)} />}
    </section>
  )
}

function ComparePlayer({ s, startStep }: { s: Street; startStep?: number }) {
  const t = useT()
  const after = s.after!
  const state = usePlayback(s.t.length, startStep ?? Math.max(0, s.before.solar_kw.indexOf(Math.max(...s.before.solar_kw))))
  const { flows, scale } = useMemo(() => mapScale(s, [s.before, after]), [s, after])
  const voltage = useMemo(() => ({
    t: s.t,
    before_max_v: s.before.home_v.map((row) => { const xs = row.filter(finite); return xs.length ? Math.max(...xs) : null }),
    after_max_v: after.home_v.map((row) => { const xs = row.filter(finite); return xs.length ? Math.max(...xs) : null }),
  }), [s, after])
  return (
    <div className={`player compare-player ${state.playing ? '' : 'paused'}`}>
      <PlaybackControls s={s} run={s.before} scale={scale.grid} state={state} />
      <div className="mode-toggle segmented" role="group" aria-label={t('player.compare')}>
        <button className="seg" aria-pressed="true">{t('player.without', { steps: s.before.unsafe.filter(Boolean).length })}</button>
        <button className="seg" aria-pressed="true">{t('player.with', { fix: s.fix_label ?? s.fix, steps: after.unsafe.filter(Boolean).length })}</button>
      </div>
      <div className="sim-compare-grid">
        <SimMap s={s} run={s.before} flows={flows[0]} scale={scale} step={state.step} heading={t('compare.before')} tone="before" />
        <SimMap s={s} run={after} flows={flows[1]} scale={scale} step={state.step} heading={t('compare.after', { fix: s.fix_label ?? s.fix })} tone="after" />
      </div>
      <VoltageCompare voltage={voltage} label={s.fix_label ?? s.fix} vmax={s.limits_v.max} step={state.step} />
    </div>
  )
}

function ForecastPlayer({ s, startStep }: { s: Street; startStep?: number }) {
  const t = useT()
  const state = usePlayback(s.t.length, startStep ?? Math.max(0, s.before.solar_kw.indexOf(Math.max(...s.before.solar_kw))))
  const { flows, scale } = useMemo(() => mapScale(s, [s.before]), [s])
  return (
    <div className={`player forecast-player ${state.playing ? '' : 'paused'}`}>
      <PlaybackControls s={s} run={s.before} scale={scale.grid} state={state} />
      <div className="forecast-sim-grid">
        <div className="forecast-map">
          <h3>{t('charts.sim_title')}</h3>
          <p className="card-sub">{t('charts.sim_intro')}</p>
          <SimMap s={s} run={s.before} flows={flows[0]} scale={scale} step={state.step} heading={t('charts.now', { time: s.t[state.step] })} tone="before" />
        </div>
        <StreetDayCharts street={s} run={s.before} step={state.step} />
      </div>
    </div>
  )
}

function StandardPlayer({ s, startStep, compact }: { s: Street; startStep?: number; compact?: boolean }) {
  const t = useT()
  const n = s.t.length
  const [step, setStep] = useState(() => startStep ?? Math.max(0, s.before.solar_kw.indexOf(Math.max(...s.before.solar_kw))))
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1)
  const [mode, setMode] = useState<'before' | 'after'>(s.after ? 'after' : 'before')
  const [home, setHome] = useState<number | null>(null)
  const run: StreetRun = mode === 'after' && s.after ? s.after : s.before

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => setStep((k) => (k + 1) % n), 1000 / (STEPS_PER_SECOND * speed))
    return () => clearInterval(id)
  }, [playing, speed, n])

  const flows = useMemo(() => homeFlows(s, run), [s, run])
  // scales fixed for the whole day and both runs, so a change on screen is a change in the street
  const scale = useMemo(() => {
    const runs = [s.before, ...(s.after ? [s.after] : [])]
    const grid = Math.max(1, ...runs.flatMap((r) => [...r.trafo_kw.map(Math.abs), ...r.solar_kw]))
    const phase = Math.max(1, ...runs.flatMap((r) => r.trafo_kw.map((_, k) => Math.max(...phaseKw(s, r, k).map(Math.abs)))))
    const home = Math.max(0.5, ...flows.net.flat().map(Math.abs))
    return { grid, phase, home }
  }, [s, flows])
  const dist = useMemo(() => { const d = depth(s); return s.homes.map((h) => d.get(h.node) ?? 0) }, [s])
  const kwp = useMemo(() => s.homes.map((h) => h.kwp), [s])

  const b = balance(s, run, step)
  const ph = phaseKw(s, run, step)
  const vs = run.home_v[step]
  const now: HomeNow[] = useMemo(() => vs.map((v, i) => ({ v, solar: flows.solar[step][i], demand: flows.demand[step][i], net: flows.net[step][i] })),
    [vs, flows, step])
  const solved = vs.filter(finite)
  const vmax = solved.length ? Math.max(...solved) : NaN
  const outside = (v: number | null) => finite(v) && (v > s.limits_v.max || v < s.limits_v.min)
  const over = vs.filter(outside).length
  const sending = now.filter((h) => h.net < -0.02).length
  const time = s.t[step]
  const unsafeSteps = run.unsafe.filter(Boolean).length
  const back = b.grid < 0
  const throughput = Math.max(b.solar, b.homes, Math.abs(b.grid))

  // the balance written out: what comes in equals what goes out
  const term = (k: StringKey, v: number) => `${t(k)} ${one(v)}`
  const ins = [b.solar > 0.05 && term('eq.solar', b.solar), b.grid > 0.05 && term('eq.grid_in', b.grid)].filter(Boolean)
  const outs = [term('eq.homes', b.homes), term('eq.loss', b.losses), b.grid < -0.05 && term('eq.grid_out', -b.grid)].filter(Boolean)

  return (
    <div className={`player ${playing ? '' : 'paused'}`}>
      <div className="player-top">
        <button className="play-btn" onClick={() => setPlaying((p) => !p)} aria-label={t(playing ? 'player.pause' : 'player.play')}>
          {playing
            ? <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="4" y="3" width="4" height="14" rx="1" fill="currentColor" /><rect x="12" y="3" width="4" height="14" rx="1" fill="currentColor" /></svg>
            : <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3 L17 10 L5 17 Z" fill="currentColor" /></svg>}
        </button>
        <div className="clock" aria-live="off">
          <span className="time">{time}</span>
          <span className="phase-of-day">{t(dayPart(time))}</span>
        </div>
        <div className="scrub">
          <DayStrip t={s.t} grid={run.trafo_kw} solar={run.solar_kw} unsafe={run.unsafe} maxKw={scale.grid} step={step}
            onStep={(k) => { setStep(k); setPlaying(false) }} />
        </div>
        <div className="speed segmented" role="group" aria-label={t('player.speed')}>
          {SPEEDS.map((v) => (
            <button key={v} className="seg" aria-pressed={speed === v} onClick={() => setSpeed(v)}>{`${v}×`}</button>
          ))}
        </div>
      </div>

      {s.after && (
        <div className="mode-toggle segmented" role="group" aria-label={t('player.compare')}>
          <button className="seg" aria-pressed={mode === 'before'} onClick={() => setMode('before')}>
            {t('player.without', { steps: s.before.unsafe.filter(Boolean).length })}
          </button>
          <button className="seg" aria-pressed={mode === 'after'} onClick={() => setMode('after')}>
            {t('player.with', { fix: s.fix_label ?? s.fix, steps: s.after.unsafe.filter(Boolean).length })}
          </button>
        </div>
      )}

      <StreetView phase={run.home_phase} dist={dist} kwp={kwp} now={now} phaseKw={ph} grid={b.grid}
        scale={scale} limits={s.limits_v} trafoKva={s.trafo_kva} loadingPct={run.trafo_loading_pct[step]}
        selected={home} onHome={setHome}
        label={t('player.map_label', { time, over, total: s.homes.length, vmax: Number.isFinite(vmax) ? one(vmax) : '—' })} />

      <ul className="legend sv-legend">
        {(['ok', 'near', 'over', 'under'] as const).map((c) => (
          <li key={c}><span className={`roof-key v-${c}`} />{t(`player.v_${c}` as StringKey)}</li>
        ))}
        <li><span className="flow-key back" />{t('sv.key_back')}</li>
        <li><span className="flow-key draw" />{t('sv.key_draw')}</li>
        <li><span className="panel-key" />{t('player.key_panel')}</li>
      </ul>

      {home !== null && (
        <HomeCard home={home} phase={run.home_phase[home]} kwp={kwp[home]} now={now[home]} shared={flows.shared[home]}
          limits={s.limits_v} onClose={() => setHome(null)} />
      )}

      <p className="flow-eq" data-numbers="balance">
        <span className="label">{t('eq.title')}</span> {ins.join(' + ') || '0'} = {outs.join(' + ')} kW
      </p>

      <div className="readouts" data-numbers="street now">
        <div className={`readout ${back ? 'tone-back' : 'tone-draw'}`}>
          <span className="k">{t(back ? 'player.to_grid' : 'player.from_grid')}</span>
          <span className="v"><Num v={Math.abs(b.grid)} fmt={one} /> kW</span>
          <span className="sub">{t('player.trafo_load', { pct: Math.round(run.trafo_loading_pct[step]) })}</span>
        </div>
        <div className="readout">
          <span className="k">{t('player.solar')}</span>
          <span className="v sun"><Num v={b.solar} fmt={one} /> kW</span>
          <span className="sub">{t('player.homes_use', { kw: one(b.homes) })}</span>
        </div>
        <div className="readout">
          <span className="k">{t('sv.homes_back')}</span>
          <span className={`v ${sending ? 'sun' : ''}`}>{sending}<small className="sub">{` / ${s.homes.length}`}</small></span>
          <span className="sub">{t('sv.homes_back_sub')}</span>
        </div>
        <div className="readout">
          <span className="k">{t('player.highest')}</span>
          <span className={`v ${vmax > s.limits_v.max ? 'act' : vmax < s.limits_v.min ? 'under' : 'ok'}`}>
            {Number.isFinite(vmax) ? <><Num v={vmax} fmt={volts} /> V</> : '—'}
          </span>
          <span className="sub">{t('player.limit', { min: volts(s.limits_v.min), max: volts(s.limits_v.max) })}</span>
        </div>
        <div className="readout">
          <span className="k">{t('player.homes_out')}</span>
          <span className={`v ${over ? 'act' : 'ok'}`}>{over}<small className="sub">{` / ${s.homes.length}`}</small></span>
          <div className="mini-meter" aria-hidden="true"><i style={{ width: `${(over / s.homes.length) * 100}%` }} /></div>
        </div>
        <div className="readout">
          <span className="k">{t('player.losses')}</span>
          <span className="v"><Num v={b.losses} fmt={one} /> kW</span>
          <span className="sub">{throughput > 0.5 ? t('player.losses_sub', { pct: one((b.losses / throughput) * 100) }) : t('player.losses_none')}</span>
        </div>
      </div>

      {!compact && (
        <section className="sp-card phase-lanes" data-numbers="phases at the transformer">
          <header className="sp-head">
            <span className="label">{t('player.phase_title')} <Prov kind="modeled" /></span>
            <span className="muted">{t('player.phase_sub')}</span>
          </header>
          {PHASES.map((p, k) => {
            const w = Math.min(50, (Math.abs(ph[k]) / scale.phase) * 50)
            const dir = ph[k] < -0.05 ? 'back' : ph[k] > 0.05 ? 'draw' : 'idle'
            const mine = run.home_phase.map((q, i) => (q === p ? i : -1)).filter((i) => i >= 0)
            return (
              <div key={p} className={`lane ${dir}`}>
                <b style={{ color: `var(--ph-${p.toLowerCase()})` }}>{p}</b>
                <div className="track">
                  <span className="fill" style={{ ['--c' as string]: dir === 'back' ? 'var(--sun)' : dir === 'draw' ? '#0ea5e9' : 'var(--ph-n)', left: ph[k] >= 0 ? '50%' : `${50 - w}%`, width: `${w}%` }} />
                  <i className="mid" />
                </div>
                <span className="val"><Num v={ph[k]} fmt={one} /> kW</span>
                <span className="lane-sub muted">
                  {t(dir === 'back' ? 'sv.lane_back' : dir === 'draw' ? 'sv.lane_draw' : 'flow.idle')}
                  {' · '}{t('sv.lane_counts', { back: mine.filter((i) => now[i].net < -0.02).length, out: mine.filter((i) => outside(vs[i])).length, n: mine.length })}
                </span>
              </div>
            )
          })}
          <div className="ends muted" aria-hidden="true"><span>{t('player.export')}</span><span>{t('player.import')}</span></div>
          <div className="neutral-row">
            <span className="k">{t('player.neutral')}</span>
            <span className="v"><Num v={run.neutral_a[step]} fmt={one} /> A</span>
            <span className="sub">{t('player.neutral_sub')}</span>
          </div>
        </section>
      )}


      {solved.length < vs.length && <p className="note" role="note">{t('player.nosolve_note')}</p>}
      {b.solar === 0 && b.grid >= 0 && over > 0 && <p className="note" role="note">{t('player.night_high')}</p>}
      <p className="muted">{t('player.how', { steps: unsafeSteps })} {t('player.flow_note')}</p>
    </div>
  )
}
