import type { Hosting, HostingRun } from '../api/v2types'
import { pct } from '../format'
import { useT, type StringKey } from '../i18n'
import Prov from './Prov'

/** Probabilistic hosting capacity (E1): the share of homes that can have solar, P10 to P90 over random placements. */
export default function HostingCard({ hosting }: { hosting: Hosting }) {
  const t = useT()
  const runs: [StringKey, HostingRun][] = [['plan.hosting_none', hosting.without_fix], ['plan.hosting_vv', hosting.with_volt_var]]
  return (
    <section className="card" aria-labelledby="hosting-title" data-numbers="hosting capacity">
      <h3 id="hosting-title">{t('plan.hosting_title')} <Prov kind="modeled" /></h3>
      {runs.map(([label, run]) => {
        const s = run.adoption_share
        return (
          <div key={label} className="hosting-row" data-hosting>
            <div className="label">{t(label)}</div>
            <div className="hosting-bar" aria-hidden="true">
              <span className="range" style={{ left: pct(s.p10), width: pct(s.p90 - s.p10) }} />
              <span className="mid" style={{ left: pct(s.p50) }} />
            </div>
            <p className="muted">{t('plan.hosting_value', {
              p50: pct(s.p50), p10: pct(s.p10), p90: pct(s.p90), kw: Math.round(run.installed_kw.p50),
            })}</p>
          </div>
        )
      })}
      <p className="muted">{t('plan.hosting_note', { draws: hosting.without_fix.draws })}</p>
    </section>
  )
}
