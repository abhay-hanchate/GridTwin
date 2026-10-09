import type { OutcomeDetails } from '../api/v2types'
import { useT } from '../i18n'
import Prov from './Prov'

/** Which homes move to which phase (from the CP-SAT plan, verified by the power flow). */
export default function PhasePlan({ moves }: { moves: NonNullable<OutcomeDetails['phase_moves']> }) {
  const t = useT()
  return (
    <section className="card" data-numbers="phase moves">
      <h3 id="phase-title">{t('fixes.phase_title')} <Prov kind="modeled" /></h3>
      <div className="table-scroll">
        <table className="data-table" aria-labelledby="phase-title">
          <thead><tr><th scope="col">{t('fixes.phase_home')}</th><th scope="col">{t('fixes.phase_from')}</th><th scope="col">{t('fixes.phase_to')}</th></tr></thead>
          <tbody>
            {moves.map((m) => (
              <tr key={m.home}><td>#{m.home}</td><td>{m.from}</td><td>{m.to}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
