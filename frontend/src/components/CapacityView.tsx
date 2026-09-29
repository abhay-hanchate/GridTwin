import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useApi } from '../api'
import { duration, niceDate } from '../plain'
import type { HostingCapacityResult } from '../types'

const kw = (value: number) => `${value.toLocaleString()} kW`

export default function CapacityView() {
  const capacity = useApi<HostingCapacityResult>('/api/hosting-capacity')

  if (capacity.loading) return <div className="loading" role="status">Estimating feeder capacity across solar adoption levels…</div>
  if (capacity.error) return <div className="error" role="alert">{capacity.error}</div>
  if (!capacity.data) return null

  const result = capacity.data
  const noFix = result.capacity.without_fix
  const withFix = result.capacity.with_fix
  const chartData = result.points.map((point) => ({
    ...point,
    adoption: `${Math.round(point.pv_share * 100)}%`,
  }))

  return (
    <div className="stack">
      <div className="story-intro">
        <h2>How much rooftop solar can this feeder host?</h2>
        <p>
          GridTwin replays {niceDate(result.date)} at 10% adoption intervals, with 3 kW of panels on each participating home.
          The sweep covers {result.total_homes} homes and reports the highest tested level that meets each safety rule.
        </p>
      </div>

      <div className="capacity-cards">
        <section className="card capacity-card">
          <div className="tag">Without a new fix</div>
          <div className="capacity-value">{kw(noFix.installed_kw)}</div>
          <p>{noFix.solar_homes} of {result.total_homes} homes with rooftop solar</p>
          <p className="muted">{duration(noFix.unsafe_steps)} unsafe; no increase over the no-solar baseline</p>
        </section>
        <section className="card capacity-card recommended">
          <div className="tag">With tap +1 and smart inverters</div>
          <div className="capacity-value">{withFix.found_safe_level ? kw(withFix.installed_kw) : 'No safe level'}</div>
          <p>{withFix.found_safe_level
            ? `${withFix.solar_homes} of ${result.total_homes} homes with rooftop solar`
            : 'No tested adoption level leaves the feeder safe all day'}</p>
          <p className="muted">{duration(withFix.unsafe_steps)} unsafe at the closest tested level</p>
        </section>
      </div>

      <section className="card">
        <h2>Unsafe 15-minute intervals as solar adoption grows</h2>
        <p className="sub">The dashed line marks the unsafe intervals already present with no rooftop solar.</p>
        <div className="capacity-chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 12, right: 20, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="#e8ebe6" vertical={false} />
              <XAxis dataKey="adoption" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} width={42} tick={{ fontSize: 11 }} />
              <Tooltip
                labelFormatter={(label) => `Solar adoption: ${label}`}
                formatter={(value, name) => [`${value} intervals`, name]}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <ReferenceLine y={result.baseline_unsafe_steps} stroke="#7a8581" strokeDasharray="5 4" />
              <Line isAnimationActive={false} type="monotone" dataKey="unsafe_steps_without_fix"
                name="Without a new fix" stroke="#c8412b" strokeWidth={2} dot />
              <Line isAnimationActive={false} type="monotone" dataKey="unsafe_steps_with_fix"
                name="With tap +1 and smart inverters" stroke="#0f766e" strokeWidth={2} dot />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <p className="muted">
        Without a fix, the limit allows no more unsafe intervals than the {result.baseline_unsafe_steps}-interval no-solar baseline.
        With the fix, all 96 intervals must be safe. This is a {result.resolution_percent}%-step estimate for one modeled day
        on a benchmark feeder, not a connection approval or a surveyed utility feeder.
      </p>
    </div>
  )
}
