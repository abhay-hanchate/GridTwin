import { useEffect, useRef, useState } from 'react'
import { useApi, volts } from '../api'
import { ACTION_TEXT, actionName, duration, SCENARIO_TEXT } from '../plain'
import type { ActionsResult, GridTopology, ScenarioId, SimResult, SimStep } from '../types'
import TwinSim from './TwinSim'

const REASONS: Record<string, [string, 'good' | 'bad' | 'warn' | '']> = {
  clears_all_violations: ['Safe all day', 'good'],
  reduces_violations: ['Helps, but not enough', 'warn'],
  does_not_help: ['Does not help', 'bad'],
  lowers_peak_voltage: ['Lowers the noon peak', ''],
  lowers_evening_voltage: ['Also lowers evening voltage', 'warn'],
  wastes_solar: ['Throws away solar', 'bad'],
}

const kw = (v: number) => `${Math.round(Math.abs(v))} kW`

/** Plain sentence: what the chosen fix is physically doing at this moment. */
function doingText(kind: string, s: SimStep): string {
  const sun = s.pv_available_kw > 1
  switch (kind) {
    case 'tap':
      return `The transformer is set ${s.tap_pos === 1 ? 'one notch' : `${s.tap_pos} notches`} lower all day, so every home receives ${(2.5 * s.tap_pos).toFixed(1)}% less voltage.`
    case 'volt_var':
      return sun
        ? `Every solar inverter is absorbing reactive power (${Math.round(s.inverter_kvar)} kvar in total), which pulls the voltage down. All ${kw(s.pv_kw)} of solar still reaches the grid.`
        : 'No sun right now, so the inverters are idle.'
    case 'combined':
      return `The transformer is one notch lower (−2.5%)${sun ? `, and the inverters are absorbing ${Math.round(s.inverter_kvar)} kvar. All ${kw(s.pv_kw)} of solar is used, nothing is thrown away.` : '. No sun right now, so the inverters are idle.'}`
    case 'curtailment':
      return sun
        ? `The panels could make ${kw(s.pv_available_kw)}, but only ${kw(s.pv_kw)} is allowed out: ${kw(s.pv_available_kw - s.pv_kw)} of clean power is being thrown away right now.`
        : 'No sun right now, so nothing is being thrown away.'
    case 'battery':
      if (s.battery_kw > 0.5) return `The battery is charging at ${kw(s.battery_kw)}, soaking up power to pull the voltage down.`
      if (s.battery_kw < -0.5) return `The battery is giving back ${kw(s.battery_kw)} while there is room below the limit.`
      return 'The battery is idle: voltage is not close enough to the limit to need it.'
    default:
      return ''
  }
}

function FixSimulator({ scenario, action, grid }: { scenario: ScenarioId; action: string; grid: GridTopology }) {
  const sim = useApi<SimResult>(`/api/fix-sim?scenario=${scenario}&action=${action}`)
  if (sim.loading) return <div className="loading" role="status">Replaying the whole day with this fix… (about 15 seconds the first time)</div>
  if (sim.error) return <div className="error" role="alert">{sim.error}</div>
  if (!sim.data) return null
  const d = sim.data
  const b = d.before.summary
  const a = d.after.summary
  const safe = a.violation_steps === 0 && b.violation_steps > 0

  return (
    <>
      <div className="impact">
        <div className="impact-card">
          <div className="l">Unsafe time</div>
          <div className="v"><s>{duration(b.violation_steps)}</s> → <span className={a.violation_steps ? 'bad' : 'good'}>{duration(a.violation_steps)}</span></div>
        </div>
        <div className="impact-card">
          <div className="l">Highest voltage</div>
          <div className="v"><s>{volts(b.max_vm_pu)} V</s> → <span className={a.max_vm_pu > d.limits.vm_max_pu ? 'bad' : 'good'}>{volts(a.max_vm_pu)} V</span></div>
        </div>
        <div className="impact-card">
          <div className="l">Lowest voltage</div>
          <div className="v"><s>{volts(b.min_vm_pu)} V</s> → <span className={a.min_vm_pu < d.limits.vm_min_pu ? 'bad' : ''}>{volts(a.min_vm_pu)} V</span></div>
        </div>
        <div className="impact-card">
          <div className="l">Solar thrown away</div>
          <div className="v"><span className={a.curtailed_kwh > 0 ? 'bad' : 'good'}>{Math.round(a.curtailed_kwh)} kWh</span></div>
        </div>
        <div className={`impact-card verdict-mini ${safe ? 'good' : 'bad'}`}>
          {safe ? '✓ Safe all day' : a.violation_steps < b.violation_steps ? 'Better, but still unsafe' : 'Not good enough'}
        </div>
      </div>
      <TwinSim sim={d} grid={grid} leftTitle="Without the fix" rightTitle={`With: ${actionName(action, d.label ?? action)}`}
        doing={(s) => doingText(d.kind ?? '', s)} />
    </>
  )
}

export default function FixesView({ scenario }: { scenario: ScenarioId }) {
  const res = useApi<ActionsResult>(`/api/actions?scenario=${scenario}`)
  const grid = useApi<GridTopology>(`/api/grid?scenario=${scenario}`)
  const [chosen, setChosen] = useState<string | null>(null)
  const top = useRef<HTMLDivElement>(null)
  useEffect(() => setChosen(null), [scenario])

  if (res.loading || grid.loading) return <div className="loading" role="status">Testing every fix across the whole day…</div>
  if (res.error || grid.error) return <div className="error" role="alert">{res.error ?? grid.error}</div>
  if (!res.data || !grid.data) return null
  const r = res.data
  const worst = Math.max(r.before.violation_steps, 1)
  const best = r.actions.find((a) => a.action_id === r.verdict.recommended)
  const selected = chosen ?? best?.action_id ?? r.actions[0].action_id
  const pick = (id: string) => { setChosen(id); top.current?.scrollIntoView({ behavior: 'smooth' }) }

  return (
    <>
      <div className="how-strip">
        <div><b>1</b> Take the same real day for the same street</div>
        <div><b>2</b> Change one setting in the computer copy</div>
        <div><b>3</b> Replay all 96 moments of the day with physics</div>
        <div><b>4</b> Compare: is it safe every minute? what did it cost?</div>
      </div>

      <div className={`verdict ${r.verdict.safe_action_found ? 'ok' : 'fail'}`}>
        <span className="icon" aria-hidden>{r.verdict.safe_action_found ? '✓' : '!'}</span>
        <div>
          {best
            ? <>Best fix: {actionName(best.action_id, best.label)}. Safe all day, {Math.round(best.cost.curtailed_kwh)} kWh of solar thrown away.</>
            : r.before.violation_steps === 0
              ? <>The street is already safe all day; no fix is needed.</>
              : <>No fix is enough here. The closest, "{actionName(r.actions[0].action_id, r.actions[0].label)}", still leaves {duration(r.actions[0].remaining_violation_steps)} unsafe.</>}
          <small>{SCENARIO_TEXT[scenario].long}. Without any fix the street is unsafe for {duration(r.before.violation_steps)}.</small>
        </div>
      </div>

      <div className="card" ref={top}>
        <h2>Fix simulator: watch a fix work</h2>
        <p className="sub">Pick a fix. Both maps replay the same day; press play and compare. {ACTION_TEXT[selected]?.how}</p>
        <div className="segmented fix-picker" role="group" aria-label="Fix to simulate">
          {r.actions.map((a) => (
            <button key={a.action_id} aria-pressed={selected === a.action_id}
              className={`seg ${selected === a.action_id ? 'active' : ''}`} onClick={() => setChosen(a.action_id)}>
              {a.acceptable ? '✓ ' : ''}{actionName(a.action_id, a.label)}
            </button>
          ))}
        </div>
        <FixSimulator key={`${scenario}-${selected}`} scenario={scenario} action={selected} grid={grid.data} />
      </div>

      <h2 className="section-title">All 7 fixes compared</h2>
      <div className="actions">
        {r.actions.map((a) => {
          const winner = a.action_id === r.verdict.recommended
          const after = a.remaining_violation_steps
          return (
            <div key={a.action_id} className={`card action ${winner ? 'winner' : ''}`}>
              <div className="rank" title={a.rank ? `Rank ${a.rank} among safe fixes` : 'Not safe all day'}>{a.rank ?? '✕'}</div>
              <div>
                <h3>{actionName(a.action_id, a.label)}</h3>
                <p className="how">{ACTION_TEXT[a.action_id]?.how}</p>
                <div className="chips">
                  {a.reason_codes.map((c) => {
                    const [text, tone] = REASONS[c] ?? [c, '']
                    return <span key={c} className={`chip ${tone}`}>{text}</span>
                  })}
                </div>
              </div>
              <div className="col">
                <div className="bar-label"><span>Unsafe time left</span><b>{duration(after)}</b></div>
                <div className="bar">
                  <span style={{ width: `${(after / worst) * 100}%`, background: after ? 'var(--unsafe)' : 'var(--safe)', minWidth: after ? 4 : 0 }} />
                </div>
                <div className="muted" style={{ marginTop: 6 }}>
                  was {duration(a.before.violation_steps)} · voltage now {volts(a.after.min_vm_pu)}–{volts(a.after.max_vm_pu)} V
                </div>
              </div>
              <div className="col metric">
                <div>Solar thrown away <b>{Math.round(a.cost.curtailed_kwh)} kWh</b></div>
                <button className="link-btn" onClick={() => pick(a.action_id)}>▶ Simulate this fix</button>
              </div>
            </div>
          )
        })}
      </div>
      <p className="muted" style={{ marginTop: 12 }}>
        Safe fixes are ranked by how much solar they throw away, then how much battery they need, then wire losses.
        ✕ means the fix leaves some unsafe time. A transformer setting is changed once for the season, not every hour.
      </p>
    </>
  )
}
