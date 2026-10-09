import type { Headroom } from '../api/v2types'
import { bindingText } from '../fixes'
import { one, pct } from '../format'
import { useT, type StringKey } from '../i18n'
import Prov from './Prov'

/** Extra rooftop solar each phase can take near the transformer and at the far end (E2), beside the flat state caps. */
export default function HeadroomTable({ headroom }: { headroom: Headroom }) {
  const t = useT()
  const rows = Object.entries(headroom.locations).flatMap(([where, loc]) =>
    Object.entries(loc.phases).map(([phase, h]) => ({ where, node: loc.node, phase, h })))
  return (
    <>
      <section className="card" data-numbers="headroom">
        <h3 id="headroom-title">{t('plan.headroom_title')} <Prov kind="modeled" /></h3>
        <p className="muted">{t('plan.headroom_base', { share: pct(headroom.adoption), steps: headroom.baseline_unsafe_steps })}</p>
        <div className="table-scroll">
          <table className="data-table" aria-labelledby="headroom-title">
            <thead>
              <tr>
                {(['col_where', 'col_phase', 'col_no_worse', 'col_strict', 'col_limit'] as const)
                  .map((k) => <th key={k} scope="col">{t(`plan.${k}`)}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map(({ where, node, phase, h }) => (
                <tr key={`${where}-${phase}`}>
                  <th scope="row">{t(`plan.where_${where}` as StringKey, { node })}</th>
                  <td>{phase}</td>
                  <td>{one(h.no_worse_kw)}</td>
                  <td>{one(h.strict_kw)}</td>
                  <td>{h.binding_limit ? bindingText(t, h.binding_limit) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">{t('plan.headroom_note')}</p>
      </section>
      <section className="card" data-numbers="state caps">
        <h3 id="caps-title">{t('plan.caps_title')} <Prov kind="benchmark" /></h3>
        <p className="muted">{t('plan.caps_installed', { kw: one(headroom.installed_kw) })}</p>
        <div className="table-scroll">
          <table className="data-table" aria-labelledby="caps-title">
            <thead>
              <tr>
                {(['col_state', 'col_cap_pct', 'col_cap_kw', 'col_share', 'col_status'] as const)
                  .map((k) => <th key={k} scope="col">{t(`plan.${k}`)}</th>)}
              </tr>
            </thead>
            <tbody>
              {Object.entries(headroom.flat_caps).map(([state, c]) => (
                <tr key={state}>
                  <th scope="row">{state}</th>
                  <td>{c.cap_pct}</td>
                  <td>{one(c.cap_kw)}</td>
                  <td>{pct(c.installed_share_of_cap)}</td>
                  <td>{c.tag}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
