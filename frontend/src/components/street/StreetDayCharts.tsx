import { useMemo } from 'react'
import type { Street, StreetRun } from '../../api/v2types'
import { one, volts } from '../../format'
import { useT } from '../../i18n'
import Prov from '../Prov'
import { balance } from './balance'

type Props = { street: Street; run: StreetRun; step: number }
type Series = { id: string; label: string; values: (number | null)[]; tone: 'act' | 'under' | 'sun' | 'grid' }

const W = 100
const H = 64
const finite = (v: number | null): v is number => v !== null && Number.isFinite(v)

/** The two explanatory charts beside Tomorrow's street. Both share the player's current quarter-hour. */
export default function StreetDayCharts({ street, run, step }: Props) {
  const t = useT()
  const voltage = useMemo(() => run.home_v.map((row) => {
    const values = row.filter(finite)
    return { high: values.length ? Math.max(...values) : null, low: values.length ? Math.min(...values) : null }
  }), [run])
  const demand = useMemo(() => street.t.map((_, k) => balance(street, run, k).homes), [street, run])
  const high = voltage.map((v) => v.high)
  const low = voltage.map((v) => v.low)

  return (
    <div className="street-day-charts">
      <DayChart title={t('charts.voltage_title')} description={t('charts.voltage_intro')}
        ariaLabel={t('charts.voltage_label', { time: street.t[step] })} times={street.t} step={step}
        series={[
          { id: 'highest', label: t('charts.highest'), values: high, tone: 'act' },
          { id: 'lowest', label: t('charts.lowest'), values: low, tone: 'under' },
        ]}
        rules={[{ value: street.limits_v.max, label: `${volts(street.limits_v.max)} V` }, { value: street.limits_v.min, label: `${volts(street.limits_v.min)} V` }]}
        current={`${high[step] === null ? '—' : `${volts(high[step]!)} V`} / ${low[step] === null ? '—' : `${volts(low[step]!)} V`}`} />
      <DayChart title={t('charts.why_title')} description={t('charts.why_intro')}
        ariaLabel={t('charts.why_label', { time: street.t[step] })} times={street.t} step={step}
        series={[
          { id: 'demand', label: t('charts.demand'), values: demand, tone: 'grid' },
          { id: 'solar', label: t('charts.solar'), values: run.solar_kw, tone: 'sun' },
        ]}
        current={`${one(demand[step])} / ${one(run.solar_kw[step])} kW`} />
    </div>
  )
}

function DayChart({ title, description, ariaLabel, times, step, series, rules = [], current }: {
  title: string
  description: string
  ariaLabel: string
  times: string[]
  step: number
  series: Series[]
  rules?: { value: number; label: string }[]
  current: string
}) {
  const values = [...series.flatMap((s) => s.values.filter(finite)), ...rules.map((r) => r.value)]
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const pad = Math.max(1, (rawMax - rawMin) * 0.08)
  const lo = Math.max(0, rawMin - pad)
  const hi = rawMax + pad
  const x = (i: number) => ((i + 0.5) * W) / times.length
  const y = (v: number) => H - ((v - lo) / Math.max(1, hi - lo)) * H
  const points = (xs: (number | null)[]) => xs.flatMap((v, i) => finite(v) ? [`${x(i).toFixed(2)},${y(v).toFixed(2)}`] : []).join(' ')

  return (
    <section className="day-chart" data-numbers={title}>
      <header className="day-chart-head">
        <div><h3>{title} <Prov kind="modeled" /></h3><p>{description}</p></div>
        <strong>{times[step]} · {current}</strong>
      </header>
      <svg className="day-chart-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={ariaLabel}>
        <rect className="chart-bg" x="0" y="0" width={W} height={H} />
        {[0.25, 0.5, 0.75].map((p) => <line key={p} className="chart-grid" x1="0" x2={W} y1={H * p} y2={H * p} vectorEffect="non-scaling-stroke" />)}
        {rules.map((rule) => <line key={rule.label} className="chart-rule" x1="0" x2={W} y1={y(rule.value)} y2={y(rule.value)} vectorEffect="non-scaling-stroke" />)}
        {series.map((s) => <polyline key={s.id} data-series={s.id} className={`chart-series tone-${s.tone}`} points={points(s.values)} vectorEffect="non-scaling-stroke" />)}
        <line className="chart-playhead" x1={x(step)} x2={x(step)} y1="0" y2={H} vectorEffect="non-scaling-stroke" />
        {series.map((s) => finite(s.values[step]) && <circle key={s.id} className={`chart-dot tone-${s.tone}`} cx={x(step)} cy={y(s.values[step]!)} r="1.6" vectorEffect="non-scaling-stroke" />)}
      </svg>
      <div className="day-chart-axis" aria-hidden="true"><span>{times[0]}</span><span>{times[Math.floor(times.length / 2)]}</span><span>{times.at(-1)}</span></div>
      <p className="day-chart-legend">
        {series.map((s) => <span key={s.id}><i className={`tone-${s.tone}`} />{s.label}</span>)}
        {rules.length > 0 && <span><i className="rule" />{rules.map((r) => r.label).join(' / ')}</span>}
      </p>
    </section>
  )
}
