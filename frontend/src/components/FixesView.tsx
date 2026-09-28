import { useApi, volts } from '../api'
import { ACTION_TEXT, actionName, duration, SCENARIO_TEXT } from '../plain'
import type { ActionsResult, ScenarioId } from '../types'

const REASONS: Record<string, [string, 'good' | 'bad' | 'warn' | '']> = {
  clears_all_violations: ['Safe all day', 'good'],
  reduces_violations: ['Helps, but not enough', 'warn'],
  does_not_help: ['Does not help', 'bad'],
  lowers_peak_voltage: ['Lowers the noon peak', ''],
  lowers_evening_voltage: ['Also lowers evening voltage', 'warn'],
  wastes_solar: ['Throws away solar', 'bad'],
}

export default function FixesView({ scenario }: { scenario: ScenarioId }) {
  const res = useApi<ActionsResult>(`/api/actions?scenario=${scenario}`)
  if (res.loading) return <div className="loading">Testing every fix across the whole day…</div>
  if (res.error) return <div className="error">{res.error}</div>
  if (!res.data) return null
  const r = res.data
  const worst = Math.max(r.before.violation_steps, 1)
  const best = r.actions.find((a) => a.action_id === r.verdict.recommended)
  const closest = r.actions[0]

  return (
    <>
      <p className="how">
        <b>{SCENARIO_TEXT[scenario].long}.</b> We tried 7 fixes on the computer copy of the street. Each one is replayed
        over the whole day, and a fix only counts if the street is safe <b>every</b> minute.
      </p>
      <div className={`verdict ${r.verdict.safe_action_found ? 'ok' : 'fail'}`}>
        <span className="icon" aria-hidden>{r.verdict.safe_action_found ? '✓' : '!'}</span>
        <div>
          {best
            ? <>Best fix: {actionName(best.action_id, best.label)}. Safe all day, {Math.round(best.cost.curtailed_kwh)} kWh of solar thrown away.</>
            : r.before.violation_steps === 0
              ? <>The street is already safe all day; no fix is needed.</>
              : <>No fix is enough here. The closest, "{actionName(closest.action_id, closest.label)}", still leaves {duration(closest.remaining_violation_steps)} unsafe.</>}
          <small>
            Without any fix: unsafe for {duration(r.before.violation_steps)}, highest {volts(r.before.max_vm_pu)} V,
            lowest {volts(r.before.min_vm_pu)} V.
          </small>
        </div>
      </div>

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
                <div>Battery energy used <b>{Math.round(a.cost.battery_throughput_kwh)} kWh</b></div>
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
