import type { Outcome } from '../api/v2types'
import { one } from '../format'
import { useT } from '../i18n'
import Prov from './Prov'

/** The recommended fix with its cost lines. Rendered only when the tournament found a safe action. */
export default function FixCard({ outcome }: { outcome: Outcome }) {
  const t = useT()
  const c = outcome.cost
  return (
    <section className="card fix-card" data-recommended data-numbers="recommended fix">
      <span className="badge">{t('fixes.recommended')}</span>
      <h3>{t('fixes.safe_title', { label: outcome.label })} <Prov kind="modeled" /></h3>
      <p className="muted">{t('fixes.safe_body')}</p>
      <ul className="cost-lines">
        <li>{t('fixes.cost_curtailed', { value: one(c.curtailed_kwh) })}</li>
        <li>{t('fixes.cost_operations', { value: c.operations })}</li>
        <li>{t('fixes.cost_battery', { value: one(c.battery_throughput_kwh) })}</li>
        <li>{t('fixes.cost_margin', { value: one(c.margin_v) })}</li>
      </ul>
    </section>
  )
}
