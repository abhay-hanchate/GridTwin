import { useV2 } from '../api/v2'
import type { GateStatus, Results } from '../api/v2types'
import Measured from '../components/Measured'
import Status from '../components/Status'
import { useT, type StringKey } from '../i18n'

const STATUSES: GateStatus[] = ['pass', 'fail', 'conditional', 'not_run', 'missing']
// Plan section 3, "Explicitly not built".
const NOT_BUILT = ['gnn', 'opender', 'rl', 'llm', 'scada', 'markets'] as const

/** Proof (P9.6): how much to trust GridTwin. Everything here is read from results.json; failed gates stay visible. */
export default function Proof() {
  const t = useT()
  const results = useV2<Results>('/results')
  return (
    <div className="v2-page">
      <p className="muted">{t('proof.intro')}</p>
      <Status state={results} />
      {results.data && <ProofView r={results.data} />}
      <section className="card">
        <h3>{t('proof.not_built_title')}</h3>
        <ul>{NOT_BUILT.map((k) => <li key={k}>{t(`proof.not_built.${k}` as StringKey)}</li>)}</ul>
      </section>
    </div>
  )
}

function ProofView({ r }: { r: Results }) {
  const t = useT()
  const tournament = r.headlines.tournament_15_may_2019 as Record<string, string> | undefined
  return (
    <>
      <section className="card" aria-labelledby="proof-summary">
        <h3 id="proof-summary">{t('proof.summary_title')}</h3>
        <ul className="gate-summary">
          {STATUSES.filter((s) => r.summary[s]).map((s) => (
            <li key={s} className={`gate-${s}`}>{t(`proof.status.${s}` as StringKey)}: {r.summary[s]}</li>
          ))}
        </ul>
        <p className="muted">{t('proof.generated', { at: r.generated_at, hash: r.git_hash })}</p>
      </section>

      <section className="card">
        <h3 id="gates-title">{t('proof.gates_title')}</h3>
        <div className="table-scroll">
          <table className="data-table gate-table" aria-labelledby="gates-title">
            <thead>
              <tr>{(['col_gate', 'col_status', 'col_measured', 'col_threshold', 'col_source'] as const)
                .map((k) => <th key={k} scope="col">{t(`proof.${k}`)}</th>)}</tr>
            </thead>
            <tbody>
              {r.gates.map((g) => (
                <tr key={g.gate} data-status={g.status} className={`gate-${g.status}`}>
                  <th scope="row">{g.gate} {g.name}</th>
                  <td><span className={`gate-badge gate-${g.status}`}>{t(`proof.status.${g.status}` as StringKey)}</span></td>
                  <td><Measured value={g.measured} />{g.note && <p className="gate-note">{g.note}</p>}</td>
                  <td>{g.threshold}</td>
                  <td>
                    {g.provenance && <p>{g.provenance}</p>}
                    {g.command && <code>{g.command}</code>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h3 id="bakeoff-title">{t('proof.bakeoff_title')}</h3>
        <p className="muted">{t('proof.bakeoff_intro')}</p>
        <div className="table-scroll">
          <table className="data-table" aria-labelledby="bakeoff-title">
            <thead>
              <tr>{(['col_component', 'col_winner', 'col_rule', 'col_split'] as const)
                .map((k) => <th key={k} scope="col">{t(`proof.${k}`)}</th>)}</tr>
            </thead>
            <tbody>
              {r.bakeoffs.map((b) => (
                <tr key={b.component}>
                  <th scope="row">{b.component}</th>
                  <td><Measured value={b.winner} /></td>
                  <td>{b.rule}</td>
                  <td>{b.split}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {tournament && (
        <section className="card">
          <h3>{t('proof.tournament_title')}</h3>
          <dl className="measured">
            {Object.entries(tournament).map(([rule, text]) => <div key={rule}><dt>{rule}</dt><dd>{text}</dd></div>)}
          </dl>
        </section>
      )}
    </>
  )
}
