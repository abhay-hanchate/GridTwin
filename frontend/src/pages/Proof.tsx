import { useV2 } from '../api/v2'
import type { Gate, GateStatus, Results } from '../api/v2types'
import type { Area } from '../app/areas'
import Explainer, { NextStep } from '../components/Explainer'
import Measured from '../components/Measured'
import Status from '../components/Status'
import { useT, type StringKey } from '../i18n'

const STATUSES: GateStatus[] = ['pass', 'fail', 'conditional', 'not_run', 'missing']
// Plan section 3, "Explicitly not built".
const NOT_BUILT = ['gnn', 'opender', 'rl', 'llm', 'scada', 'markets'] as const
// The questions a reader asks, and the gates that answer each one.
const QUESTIONS: { id: string; gates: string[] }[] = [
  { id: 'physics', gates: ['G1', 'G5'] },
  { id: 'forecast', gates: ['G2', 'G3', 'G4', 'G7'] },
  { id: 'risk', gates: ['G8'] },
  { id: 'use', gates: ['G6'] },
]

/** Proof (P9.6): how much to trust GridTwin, as four plain questions. Everything is read from results.json and
 *  failed checks stay visible. */
export default function Proof({ go }: { go?: (area: Area) => void }) {
  const t = useT()
  const results = useV2<Results>('/results')
  return (
    <div className="v2-page">
      <header className="page-hero">
        <span className="kicker">{t('journey.step', { n: 5 })} · {t('area.proof')}</span>
        <h2>{t('proof.page_title')}</h2>
        <p>{t('proof.page_intro')}</p>
      </header>
      <Status state={results} />
      {results.data && <ProofView r={results.data} />}
      <details className="more">
        <summary>{t('proof.not_built_title')}</summary>
        <ul>{NOT_BUILT.map((k) => <li key={k}>{t(`proof.not_built.${k}` as StringKey)}</li>)}</ul>
      </details>
      <Explainer groups={['gate', 'prov']} />
      <NextStep to="home" go={go} />
    </div>
  )
}

function Ring({ passed, total }: { passed: number; total: number }) {
  const r = 50
  const c = 2 * Math.PI * r
  return (
    <svg className="ring" viewBox="0 0 120 120" aria-hidden="true">
      <circle className="bg" cx="60" cy="60" r={r} fill="none" strokeWidth="12" />
      <circle className="fg" cx="60" cy="60" r={r} fill="none" strokeWidth="12" strokeDasharray={`${(passed / Math.max(total, 1)) * c} ${c}`}
        transform="rotate(-90 60 60)" />
      <text x="60" y="68" textAnchor="middle">{`${passed}/${total}`}</text>
    </svg>
  )
}

function ProofView({ r }: { r: Results }) {
  const t = useT()
  const byId = new Map(r.gates.map((g) => [g.gate, g]))
  const passed = r.gates.filter((g) => g.status === 'pass').length
  return (
    <>
      <section className="card proof-score" aria-labelledby="proof-summary">
        <Ring passed={passed} total={r.gates.length} />
        <div>
          <h3 id="proof-summary">{t('proof.summary_title')}</h3>
          <ul className="gate-summary">
            {STATUSES.filter((s) => r.summary[s]).map((s) => (
              <li key={s} className={`gate-${s}`}>{t(`proof.status.${s}` as StringKey)}: {r.summary[s]}</li>
            ))}
          </ul>
          <p className="muted">{t('proof.score_line')}</p>
          <p className="muted">{t('proof.generated', { at: r.generated_at, hash: r.git_hash })}</p>
        </div>
      </section>

      {QUESTIONS.map((q) => (
        <section key={q.id} className="proof-q" aria-labelledby={`pq-${q.id}`}>
          <div className="q-head">
            <span className="no">?</span>
            <div><h3 id={`pq-${q.id}`}>{t(`proof.q_${q.id}` as StringKey)}</h3><p>{t(`proof.q_${q.id}_intro` as StringKey)}</p></div>
          </div>
          <div className="gate-cards">
            {q.gates.map((id) => byId.get(id)).filter((g): g is Gate => g !== undefined).map((g) => <GateCard key={g.gate} g={g} />)}
          </div>
        </section>
      ))}

      <details className="more">
        <summary>{t('proof.bakeoff_title')}</summary>
        <p className="muted">{t('proof.bakeoff_intro')}</p>
        <div className="table-scroll">
          <table className="data-table" aria-label={t('proof.bakeoff_title')}>
            <thead>
              <tr>{(['col_component', 'col_winner', 'col_rule', 'col_split'] as const).map((k) => <th key={k} scope="col">{t(`proof.${k}`)}</th>)}</tr>
            </thead>
            <tbody>
              {r.bakeoffs.map((b) => (
                <tr key={b.component}><th scope="row">{b.component}</th><td><Measured value={b.winner} /></td><td className="wrap">{b.rule}</td>
                  <td className="wrap">{b.split}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  )
}

function GateCard({ g }: { g: Gate }) {
  const t = useT()
  return (
    <article className={`gate-card gate-${g.status}`} data-status={g.status}>
      <span className="gate-id">{g.gate}</span>
      <h4>{t(`proof.g.${g.gate}` as StringKey)}</h4>
      <span className={`gate-badge gate-${g.status}`}>{t(`proof.status.${g.status}` as StringKey)}</span>
      <p className="plain">{t(`proof.g.${g.gate}_why` as StringKey)}</p>
      {g.note && <p className="gate-note">{g.note}</p>}
      <details>
        <summary>{t('proof.details')}</summary>
        <p className="muted">{g.name}</p>
        <Measured value={g.measured} />
        <p className="muted">{t('proof.threshold', { text: g.threshold })}</p>
        {g.provenance && <p className="muted">{g.provenance}</p>}
        {g.command && <code>{g.command}</code>}
      </details>
    </article>
  )
}
