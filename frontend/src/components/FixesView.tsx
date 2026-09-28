import { useApi, volts } from '../api'
import type { ActionsResult, ScenarioId } from '../types'

const REASONS: Record<string, [string, 'good' | 'bad' | 'warn' | '']> = {
  clears_all_violations: ['Safe all day', 'good'],
  reduces_violations: ['Reduces unsafe time', 'warn'],
  does_not_help: ['Does not help', 'bad'],
  lowers_peak_voltage: ['Lowers peak voltage', ''],
  lowers_evening_voltage: ['Also lowers evening voltage', 'warn'],
  wastes_solar: ['Wastes solar energy', 'bad'],
}

export default function FixesView({ scenario }: { scenario: ScenarioId }) {
  const res = useApi<ActionsResult>(`/api/actions?scenario=${scenario}`)
  if (res.loading) return <div className="loading">Testing every fix across all 96 steps…</div>
  if (res.error) return <div className="error">{res.error}</div>
  if (!res.data) return null
  const r = res.data
  const worst = Math.max(r.before.violation_steps, 1)

  return (
    <>
      <div className={`verdict ${r.verdict.safe_action_found ? 'ok' : 'fail'}`}>
        <span className="icon" aria-hidden>{r.verdict.safe_action_found ? '✓' : '!'}</span>
        <div>
          {r.verdict.message}
          <small>
            Before any fix: {r.before.violation_steps} unsafe steps, peak {volts(r.before.max_vm_pu)} V, lowest {volts(r.before.min_vm_pu)} V
            (±{r.band}% band). A fix counts only if every one of the 96 steps is safe.
          </small>
        </div>
      </div>

      <div className="actions">
        {r.actions.map((a) => {
          const winner = a.action_id === r.verdict.recommended
          const after = a.remaining_violation_steps
          return (
            <div key={a.action_id} className={`card action ${winner ? 'winner' : ''}`}>
              <div className="rank">{a.rank ?? '–'}</div>
              <div>
                <h3>{a.label}</h3>
                <div className="chips">
                  {a.reason_codes.map((c) => {
                    const [text, tone] = REASONS[c] ?? [c, '']
                    return <span key={c} className={`chip ${tone}`}>{text}</span>
                  })}
                </div>
              </div>
              <div className="col">
                <div className="bar-label"><span>Unsafe steps</span><span>{r.before.violation_steps} → <b>{after}</b></span></div>
                <div className="bar">
                  <span style={{ width: `${(after / worst) * 100}%`, background: after ? 'var(--unsafe)' : 'var(--safe)', minWidth: after ? 4 : 0 }} />
                </div>
                <div className="muted" style={{ marginTop: 6 }}>
                  Peak {volts(a.after.max_vm_pu)} V · lowest {volts(a.after.min_vm_pu)} V
                </div>
              </div>
              <div className="col metric">
                <div>Solar wasted <b>{Math.round(a.cost.curtailed_kwh)} kWh</b></div>
                <div>Battery use <b>{Math.round(a.cost.battery_throughput_kwh)} kWh</b></div>
                <div>Line losses <b>{a.cost.losses_kwh.toFixed(1)} kWh</b></div>
              </div>
            </div>
          )
        })}
      </div>
      <p className="muted" style={{ marginTop: 12 }}>
        Transformer taps are off-load, so one setting holds for the whole day. Safe fixes are ranked by solar wasted,
        then battery use, then line losses. The battery uses volt-droop control at the worst bus (#{r.worst_bus}).
      </p>
    </>
  )
}
