import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi, volts } from '../api'
import { actionName, duration, GLOSSARY, niceDate, SCENARIO_TEXT } from '../plain'
import type { ActionsResult, EarlyWarning, Insights, SummaryRow } from '../types'

type Go = (tab: 'grid' | 'fixes' | 'forecast') => void

function Step({ n, title, children, cta, onCta }: {
  n: number; title: string; children: React.ReactNode; cta?: string; onCta?: () => void
}) {
  return (
    <section className="card story-step">
      <div className="story-num">{n}</div>
      <div className="story-body">
        <h2>{title}</h2>
        {children}
        {cta && <button className="link-btn" onClick={onCta}>{cta} →</button>}
      </div>
    </section>
  )
}

export default function StoryView({ go }: { go: Go }) {
  const insights = useApi<Insights>('/api/insights')
  const summary = useApi<SummaryRow[]>('/api/summary')
  const fixes = useApi<ActionsResult>('/api/actions?scenario=S4')
  const strict = useApi<ActionsResult>('/api/actions?scenario=S5')
  const warn = useApi<EarlyWarning>('/api/early-warning')

  const bars = (summary.data ?? []).filter((r) => r.id !== 'S5').map((r) => ({
    name: SCENARIO_TEXT[r.id].short,
    already: (r.violation_steps_without_solar * 15) / 60,
    solar: (Math.max(r.violation_steps_from_solar, 0) * 15) / 60,
    end: 0.001,
    label: duration(r.violation_steps),
  }))
  const best = fixes.data?.actions.find((a) => a.action_id === fixes.data?.verdict.recommended)
  const throwAway = fixes.data?.actions.find((a) => a.action_id === 'export_cap_60')
  const allSolar = summary.data?.find((r) => r.id === 'S4')

  return (
    <div className="stack">
      <div className="story-intro">
        <h2>What happens to a street's electricity when every home gets solar?</h2>
        <p>
          GridTwin is a computer copy of a real kind of street: 99 homes on one transformer, using real electricity
          use and real voltage from homes in Mathura and real weather. Four steps explain what we found.
        </p>
      </div>

      <Step n={1} title="The street's voltage is already too high">
        {insights.data && (
          <div className="story-row">
            <div className="big-stat bad">{Math.round(insights.data.share_above_10pct * 100)}%</div>
            <p>
              Smart meters in <b>{insights.data.meters} real Mathura homes</b> show that voltage was above the safe limit
              of <b>253 V</b> for {Math.round(insights.data.share_above_10pct * 100)}% of the time in 2019. Homes are
              meant to get 230 V; the typical reading was <b>{insights.data.median_v} V</b>. There is almost no room
              left before solar arrives.
            </p>
          </div>
        )}
      </Step>

      <Step n={2} title="Rooftop solar pushes it over the edge at midday" cta="Watch it happen on the live map" onCta={() => go('grid')}>
        <p>
          At noon, solar panels make far more power than homes use, so the extra flows back into the street's wire and
          raises the voltage. Hours per day when voltage is unsafe:
        </p>
        {summary.data && (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={bars} layout="vertical" margin={{ top: 4, right: 90, left: 8, bottom: 0 }}>
              <CartesianGrid stroke="#e8ebe6" horizontal={false} />
              <XAxis type="number" unit=" h" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v, name) => (name ? (typeof v === 'number' ? duration(Math.round(v * 4)) : v) : null)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar isAnimationActive={false} dataKey="already" stackId="a" name="Unsafe even without solar" fill="#b9c2bb" />
              <Bar isAnimationActive={false} dataKey="solar" stackId="a" name="Extra unsafe time caused by solar" fill="#c8412b" />
              {/* Invisible sliver at the end of each bar carries the total, so even "No solar" gets a label. */}
              <Bar isAnimationActive={false} dataKey="end" stackId="a" fill="transparent" legendType="none" name="">
                <LabelList dataKey="label" position="right" style={{ fontSize: 12, fontWeight: 700, fill: '#16201d' }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
        {allSolar && (
          <p className="muted">
            With every home on solar the highest voltage reaches <b>{volts(allSolar.max_vm_pu)} V</b>, and solar causes{' '}
            {duration(allSolar.violation_steps_from_solar)} of the {duration(allSolar.violation_steps)} of unsafe time.
          </p>
        )}
      </Step>

      <Step n={3} title="Two cheap setting changes fix it without wasting any solar" cta="Compare all 7 fixes" onCta={() => go('fixes')}>
        {best && throwAway && (
          <div className="compare">
            <div className="compare-card good">
              <div className="tag">Best fix</div>
              <h3>{actionName(best.action_id, best.label)}</h3>
              <div className="compare-stat">Unsafe time: <b>{duration(best.before.violation_steps)} → {duration(best.remaining_violation_steps)}</b></div>
              <div className="compare-stat">Solar thrown away: <b>{Math.round(best.cost.curtailed_kwh)} kWh</b></div>
            </div>
            <div className="compare-card bad">
              <div className="tag">What utilities often do</div>
              <h3>{actionName(throwAway.action_id, throwAway.label)}</h3>
              <div className="compare-stat">Unsafe time: <b>{duration(throwAway.before.violation_steps)} → {duration(throwAway.remaining_violation_steps)}</b></div>
              <div className="compare-stat">Solar thrown away: <b>{Math.round(throwAway.cost.curtailed_kwh)} kWh</b></div>
            </div>
          </div>
        )}
        <p className="muted">
          We tested 7 possible fixes on the computer copy, each across the whole day, and only accept a fix if the street
          is safe every minute.
          {strict.data && !strict.data.verdict.safe_action_found &&
            ' Under the stricter future rule (±6%), no fix is enough, and GridTwin says so honestly instead of pretending.'}
        </p>
      </Step>

      <Step n={4} title="Our AI gives a day's warning" cta="See the forecast" onCta={() => go('forecast')}>
        {warn.data && (
          <div className="story-row">
            <div className="big-stat">{duration(warn.data.cases.p50.violation_steps)}</div>
            <p>
              From the weather forecast for <b>{niceDate(warn.data.date)}</b>, our AI predicted <b>{duration(warn.data.cases.p50.violation_steps)}</b> of
              unsafe voltage the day before, starting around {warn.data.cases.p50.first_unsafe}. The independent ERA5/PVWatts reference simulation produced{' '}
              <b>{duration(warn.data.cases.actual.violation_steps)}</b>. Demand and incoming voltage use the labelled 2019 proxy.
            </p>
          </div>
        )}
      </Step>

      <details className="card glossary">
        <summary>Words used on this site</summary>
        <dl>
          {GLOSSARY.map(([term, meaning]) => (
            <div key={term}><dt>{term}</dt><dd>{meaning}</dd></div>
          ))}
        </dl>
      </details>
    </div>
  )
}
