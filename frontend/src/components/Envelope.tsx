import type { OutcomeDetails } from '../api/v2types'
import { one } from '../format'
import { useT } from '../i18n'
import Prov from './Prov'

/** Day-ahead per-house export limits: one row per home, one column per quarter hour where a limit binds. */
export default function Envelope({ limits }: { limits: NonNullable<OutcomeDetails['export_limits']> }) {
  const t = useT()
  return (
    <section className="card" data-numbers="export limits">
      <h3 id="env-title">{t('fixes.env_title')} <Prov kind="modeled" /></h3>
      <div className="table-scroll">
        <table className="data-table" aria-labelledby="env-title">
          <thead>
            <tr><th scope="col">{t('fixes.env_home')}</th>{limits.t.map((ts) => <th key={ts} scope="col">{ts}</th>)}</tr>
          </thead>
          <tbody>
            {limits.homes.map((home, h) => (
              <tr key={home}><th scope="row">#{home}</th>{limits.kw[h].map((kw, s) => <td key={s}>{one(kw)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
