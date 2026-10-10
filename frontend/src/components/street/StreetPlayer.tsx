import { useEffect, useMemo, useState } from 'react'
import { useV2, v2Path } from '../../api/v2'
import type { Street, StreetRun } from '../../api/v2types'
import { one, volts } from '../../format'
import { useT, type StringKey } from '../../i18n'
import Prov from '../Prov'
import Status from '../Status'
import type { HomeView } from './geometry'
import StreetMap from './StreetMap'
import { homeClass } from './voltage'
import { matchWires, rootPhaseKw } from './wires'

const SPEEDS = [0.5, 1, 2] as const
const STEPS_PER_SECOND = 4                       // at 1x a day plays in 24 seconds
const PH = ['A', 'B', 'C'] as const

type Props = { network: string; rule: string; date: string | null; fix?: string; fixLabel?: string; startStep?: number; compact?: boolean }

/** The animated street: loads /street and plays the design day quarter hour by quarter hour. */
export default function StreetPlayer({ network, rule, date, fix = 'none', fixLabel, startStep, compact }: Props) {
  const street = useV2<Street>(date ? v2Path('/street', { network, rule, date, fix }) : null)
  if (!street.data) return <Status state={street} />
  return <Player key={`${street.data.date}-${street.data.rule}-${street.data.fix}`} s={fixLabel ? { ...street.data, fix_label: fixLabel } : street.data}
    startStep={startStep} compact={compact} />
}

function dayPart(time: string): StringKey {
  const h = Number(time.slice(0, 2))
  if (h < 6 || h >= 20) return 'player.night'
  if (h < 10) return 'player.morning'
  if (h < 16) return 'player.midday'
  return 'player.evening'
}

function Player({ s, startStep, compact }: { s: Street; startStep?: number; compact?: boolean }) {
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

  const homes: HomeView[] = useMemo(() => s.homes.map((h, i) => {
    const v = run.home_v[step][i]
    return { node: h.node, phase: run.home_phase[i], kwp: h.kwp, cls: homeClass(v, s.limits_v),
      title: v === null ? t('player.home_nosolve', { home: i + 1, phase: run.home_phase[i] }) : t('player.home_title', { home: i + 1, phase: run.home_phase[i], v: one(v) }) }
  }), [s, run, step, t])

  const wires = useMemo(() => matchWires(s.layout, run, step), [s, run, step])
  const phaseKw = rootPhaseKw(s.layout, run, step)
  const maxPhase = useMemo(() => Math.max(1, ...s.before.line_phase_kw.flatMap((_, i) => rootPhaseKw(s.layout, s.before, i).map(Math.abs))), [s])
  const vs = run.home_v[step]
  const solved = vs.filter((v): v is number => v !== null && Number.isFinite(v))
  const vmax = solved.length ? Math.max(...solved) : NaN
  const over = solved.filter((v) => v > s.limits_v.max || v < s.limits_v.min).length
  const trafo = run.trafo_kw[step]
  const time = s.t[step]
  const unsafeSteps = run.unsafe.filter(Boolean).length

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
          <div className="scrub-track">
            <div className="unsafe-ticks" aria-hidden="true">{run.unsafe.map((u, i) => <i key={i} className={u ? 'on' : ''} />)}</div>
            <input type="range" min={0} max={n - 1} value={step} aria-label={t('player.time')} aria-valuetext={time}
              onChange={(e) => { setStep(Number(e.target.value)); setPlaying(false) }} />
          </div>
          <div className="axis" aria-hidden="true">{[0, 24, 48, 72, n - 1].map((i) => <span key={i}>{s.t[i]}</span>)}</div>
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

      <div className="street-scroll">
        <StreetMap layout={s.layout} homes={homes} flows={wires.flows} openLines={wires.open} ties={wires.ties}
          tieTitle={t('player.key_tie')} openTitle={t('player.key_open')} selectedHome={home} onHome={setHome}
          trafoLabel={t('player.trafo', { kva: Math.round(s.trafo_kva) })} trafoSub={t('player.trafo_sub')}
          label={t('player.map_label', { time, over, total: s.homes.length, vmax: Number.isFinite(vmax) ? one(vmax) : '—' })} />
      </div>

      {home !== null && (
        <div className="home-detail" role="status">
          <span>{t('player.home_detail', { home: home + 1 })}</span>
          <span>{t('player.home_phase')} <b>{run.home_phase[home]}</b></span>
          <span>{t('player.home_v')} <b>{vs[home] === null ? '—' : `${one(vs[home]!)} V`}</b></span>
          <span>{s.homes[home].kwp > 0 ? t('player.home_solar', { kwp: one(s.homes[home].kwp) }) : t('player.home_nosolar')}</span>
          <button className="seg" onClick={() => setHome(null)}>{t('player.close')}</button>
        </div>
      )}

      <div className="readouts" data-numbers="street now">
        <div className="readout">
          <span className="k">{t(trafo >= 0 ? 'player.from_grid' : 'player.to_grid')}</span>
          <span className={`v ${trafo < 0 ? 'sun' : ''}`}>{one(Math.abs(trafo))} kW</span>
          <span className="sub">{t('player.trafo_load', { pct: Math.round(run.trafo_loading_pct[step]) })}</span>
        </div>
        <div className="readout">
          <span className="k">{t('player.solar')}</span>
          <span className="v sun">{one(run.solar_kw[step])} kW</span>
        </div>
        <div className="readout">
          <span className="k">{t('player.highest')}</span>
          <span className={`v ${vmax > s.limits_v.max ? 'act' : 'ok'}`}>{Number.isFinite(vmax) ? `${volts(vmax)} V` : '—'}</span>
          <span className="sub">{t('player.limit', { min: volts(s.limits_v.min), max: volts(s.limits_v.max) })}</span>
        </div>
        <div className="readout">
          <span className="k">{t('player.homes_out')}</span>
          <span className={`v ${over ? 'act' : 'ok'}`}>{over}<small className="sub">{` / ${s.homes.length}`}</small></span>
        </div>
        <div className="readout">
          <span className="k">{t('player.neutral')}</span>
          <span className="v">{one(run.neutral_a[step])} A</span>
          <span className="sub">{t('player.neutral_sub')}</span>
        </div>
      </div>

      {!compact && (
        <div className="phase-bars" data-numbers="phases at the transformer">
          <span className="label">{t('player.phase_title')} <Prov kind="modeled" /></span>
          {PH.map((p, k) => {
            const w = (Math.abs(phaseKw[k]) / maxPhase) * 50
            return (
              <div key={p} className="phase-bar">
                <b style={{ color: `var(--ph-${p.toLowerCase()})` }}>{p}</b>
                <div className="track">
                  <span style={{ background: `var(--ph-${p.toLowerCase()})`, left: phaseKw[k] >= 0 ? '50%' : `${50 - w}%`, width: `${w}%` }} />
                  <i className="mid" />
                </div>
                <span className="val">{one(phaseKw[k])} kW</span>
              </div>
            )
          })}
          <div className="ends muted" aria-hidden="true"><span>{t('player.export')}</span><span>{t('player.import')}</span></div>
        </div>
      )}

      <ul className="legend">
        {(['a', 'b', 'c'] as const).map((p) => (
          <li key={p}><span className="wire-key" style={{ borderColor: `var(--ph-${p})` }} />{t(`player.key_${p}` as StringKey)}</li>
        ))}
        <li><span className="wire-key n" style={{ borderColor: 'var(--ph-n)' }} />{t('player.key_n')}</li>
        {wires.ties.length > 0 && <li><span className="wire-key tie" />{t('player.key_tie')}</li>}
        {wires.open.size > 0 && <li><span className="wire-key open" />{t('player.key_open')}</li>}
        {(['ok', 'near', 'over', 'under'] as const).map((c) => (
          <li key={c}><span className="dot" style={{ background: `var(--${c === 'near' ? 'watch' : c === 'over' ? 'act' : c})` }} />{t(`player.v_${c}` as StringKey)}</li>
        ))}
        <li><span className="dot" style={{ background: 'var(--sun)', borderRadius: 2 }} />{t('player.key_panel')}</li>
      </ul>
      {solved.length < vs.length && <p className="note" role="note">{t('player.nosolve_note')}</p>}
      {run.solar_kw[step] === 0 && trafo >= 0 && over > 0 && <p className="note" role="note">{t('player.night_high')}</p>}
      <p className="muted">{t('player.how', { steps: unsafeSteps })} {t('player.flow_note')}</p>
    </div>
  )
}
