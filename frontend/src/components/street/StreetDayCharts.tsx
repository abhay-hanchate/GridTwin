import { useMemo, useState, useCallback, type PointerEvent } from 'react'
import type { Street, StreetRun } from '../../api/v2types'
import { one, volts } from '../../format'
import { useT } from '../../i18n'
import Prov from '../Prov'
import { balance } from './balance'

type Props = { street: Street; run: StreetRun; step: number; onStep?: (step: number) => void }
type Series = {
  id: string
  label: string
  values: (number | null)[]
  tone: 'act' | 'under' | 'sun' | 'grid'
  unit: string
}

const W = 460
const H = 150
const ML = 38
const MR = 14
const MT = 14
const MB = 22
const PW = W - ML - MR
const PH = H - MT - MB

const finite = (v: number | null): v is number => v !== null && Number.isFinite(v)

/** Convert a series of points into a smooth cubic Bézier SVG path */
function smoothPath(pts: { x: number; y: number }[]): string {
  if (pts.length === 0) return ''
  if (pts.length === 1) return `M ${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`
  let d = `M ${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[Math.min(pts.length - 1, i + 2)]
    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6
    d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`
  }
  return d
}

function areaPath(pts: { x: number; y: number }[], baseY: number): string {
  if (pts.length === 0) return ''
  const line = smoothPath(pts)
  const first = pts[0]
  const last = pts[pts.length - 1]
  return `${line} L ${last.x.toFixed(1)},${baseY.toFixed(1)} L ${first.x.toFixed(1)},${baseY.toFixed(1)} Z`
}

/** The two synchronized explanatory charts beside Tomorrow's street. */
export default function StreetDayCharts({ street, run, step, onStep }: Props) {
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
      <DayChart
        chartId="v-chart"
        title={t('charts.voltage_title')}
        description={t('charts.voltage_intro')}
        ariaLabel={t('charts.voltage_label', { time: street.t[step] })}
        times={street.t}
        step={step}
        onStep={onStep}
        series={[
          { id: 'highest', label: t('charts.highest'), values: high, tone: 'act', unit: 'V' },
          { id: 'lowest', label: t('charts.lowest'), values: low, tone: 'under', unit: 'V' },
        ]}
        rules={[
          { value: street.limits_v.max, label: `${volts(street.limits_v.max)} V` },
          { value: street.limits_v.min, label: `${volts(street.limits_v.min)} V` },
        ]}
        current={`${high[step] === null ? '—' : `${volts(high[step]!)} V`} / ${low[step] === null ? '—' : `${volts(low[step]!)} V`}`}
      />
      <DayChart
        chartId="p-chart"
        title={t('charts.why_title')}
        description={t('charts.why_intro')}
        ariaLabel={t('charts.why_label', { time: street.t[step] })}
        times={street.t}
        step={step}
        onStep={onStep}
        series={[
          { id: 'demand', label: t('charts.demand'), values: demand, tone: 'grid', unit: 'kW' },
          { id: 'solar', label: t('charts.solar'), values: run.solar_kw, tone: 'sun', unit: 'kW' },
        ]}
        current={`${one(demand[step])} / ${one(run.solar_kw[step])} kW`}
      />
    </div>
  )
}

function DayChart({
  chartId,
  title,
  description,
  ariaLabel,
  times,
  step,
  series,
  rules = [],
  current,
  onStep,
}: {
  chartId: string
  title: string
  description: string
  ariaLabel: string
  times: string[]
  step: number
  series: Series[]
  rules?: { value: number; label: string }[]
  current: string
  onStep?: (step: number) => void
}) {
  const [isScrubbing, setIsScrubbing] = useState(false)

  const allVals = [...series.flatMap((s) => s.values.filter(finite)), ...rules.map((r) => r.value)]
  const rawMin = allVals.length ? Math.min(...allVals) : 0
  const rawMax = allVals.length ? Math.max(...allVals) : 1
  const span = Math.max(1, rawMax - rawMin)
  const pad = span * 0.08
  const lo = Math.max(0, Math.floor(rawMin - pad))
  const hi = Math.ceil(rawMax + pad)
  const range = Math.max(1, hi - lo)

  const x = (i: number) => ML + (i * PW) / Math.max(1, times.length - 1)
  const y = (v: number) => MT + PH - ((v - lo) / range) * PH

  // Y-axis ticks
  const yTicks = useMemo(() => {
    const count = 4
    const ticks: { val: number; y: number }[] = []
    for (let i = 0; i < count; i++) {
      const val = lo + (range * i) / (count - 1)
      ticks.push({ val: Math.round(val), y: y(val) })
    }
    return ticks
  }, [lo, range])

  // Points for polyline and smooth curves
  const seriesPaths = useMemo(() => {
    return series.map((s) => {
      const validPoints: { x: number; y: number }[] = []
      s.values.forEach((v, i) => {
        if (finite(v)) validPoints.push({ x: x(i), y: y(v) })
      })
      const polyPoints = validPoints.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
      const smoothLine = smoothPath(validPoints)
      const area = areaPath(validPoints, MT + PH)
      return {
        id: s.id,
        tone: s.tone,
        polyPoints,
        smoothLine,
        area,
      }
    })
  }, [series, lo, range, times.length])

  // Scrub handler
  const handlePointer = useCallback((e: PointerEvent<SVGSVGElement>) => {
    if (!onStep) return
    const rect = e.currentTarget.getBoundingClientRect()
    const frac = (e.clientX - rect.left - (ML / W) * rect.width) / ((PW / W) * rect.width)
    const target = Math.max(0, Math.min(times.length - 1, Math.round(frac * (times.length - 1))))
    onStep(target)
  }, [onStep, times.length])

  return (
    <section className="day-chart" data-numbers={title}>
      <header className="day-chart-head">
        <div className="day-chart-title-group">
          <h3>{title} <Prov kind="modeled" /></h3>
          <p>{description}</p>
        </div>
        <div className="day-chart-live-badge">
          <span className="live-clock">{times[step]}</span>
          <strong className="live-readout">{current}</strong>
        </div>
      </header>

      <div className="day-chart-canvas-wrap">
        <svg
          className="day-chart-svg"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={ariaLabel}
          onPointerDown={(e) => {
            setIsScrubbing(true)
            e.currentTarget.setPointerCapture(e.pointerId)
            handlePointer(e)
          }}
          onPointerMove={(e) => {
            if (isScrubbing) handlePointer(e)
          }}
          onPointerUp={(e) => {
            setIsScrubbing(false)
            try { e.currentTarget.releasePointerCapture(e.pointerId) } catch { /* ignore */ }
          }}
          style={{ cursor: onStep ? 'ew-resize' : 'default' }}
        >
          <defs>
            <linearGradient id={`grad-act-${chartId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--act)" stopOpacity="0.28" />
              <stop offset="100%" stopColor="var(--act)" stopOpacity="0.0" />
            </linearGradient>
            <linearGradient id={`grad-under-${chartId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--under)" stopOpacity="0.22" />
              <stop offset="100%" stopColor="var(--under)" stopOpacity="0.0" />
            </linearGradient>
            <linearGradient id={`grad-sun-${chartId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--sun)" stopOpacity="0.32" />
              <stop offset="100%" stopColor="var(--sun)" stopOpacity="0.0" />
            </linearGradient>
            <linearGradient id={`grad-grid-${chartId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.24" />
              <stop offset="100%" stopColor="var(--brand)" stopOpacity="0.0" />
            </linearGradient>
            <filter id={`glow-${chartId}`} x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="1" stdDeviation="2" floodOpacity="0.25" />
            </filter>
          </defs>

          {/* Background surface */}
          <rect className="chart-bg" x={ML} y={MT} width={PW} height={PH} rx="6" />

          {/* Horizontal gridlines & Y labels */}
          {yTicks.map((t, idx) => (
            <g key={idx} className="chart-grid-row">
              <line className="chart-grid" x1={ML} x2={W - MR} y1={t.y} y2={t.y} vectorEffect="non-scaling-stroke" />
              <text x={ML - 6} y={t.y + 3.5} className="chart-y-label">{t.val}</text>
            </g>
          ))}

          {/* Safe limit rule lines */}
          {rules.map((rule) => {
            const ry = y(rule.value)
            return (
              <g key={rule.label} className="chart-rule-group">
                <line className="chart-rule" x1={ML} x2={W - MR} y1={ry} y2={ry} vectorEffect="non-scaling-stroke" />
                <rect x={W - MR - 46} y={ry - 7.5} width="46" height="15" rx="3.5" className="chart-rule-tag-bg" />
                <text x={W - MR - 23} y={ry + 3.5} className="chart-rule-tag-text">{rule.label}</text>
              </g>
            )
          })}

          {/* Gradient area fills under the curve */}
          {seriesPaths.map((sp) => (
            <path
              key={`area-${sp.id}`}
              className={`chart-area tone-${sp.tone}`}
              d={sp.area}
              fill={`url(#grad-${sp.tone}-${chartId})`}
            />
          ))}

          {/* Polylines for test assertions & line rendering */}
          {seriesPaths.map((sp) => (
            <polyline
              key={`poly-${sp.id}`}
              data-series={sp.id}
              className={`chart-series tone-${sp.tone}`}
              points={sp.polyPoints}
              vectorEffect="non-scaling-stroke"
            />
          ))}

          {/* Active playhead column highlight */}
          <rect
            className="chart-playhead-halo"
            x={x(step) - 6}
            y={MT}
            width="12"
            height={PH}
            rx="3"
            vectorEffect="non-scaling-stroke"
          />
          <line
            className="chart-playhead"
            x1={x(step)}
            x2={x(step)}
            y1={MT}
            y2={MT + PH}
            vectorEffect="non-scaling-stroke"
          />

          {/* Glowing dot on each series at active step */}
          {series.map((s) => {
            const v = s.values[step]
            if (!finite(v)) return null
            const cx = x(step)
            const cy = y(v)
            return (
              <g key={`dot-${s.id}`} className={`chart-dot-group tone-${s.tone}`} filter={`url(#glow-${chartId})`}>
                <circle className="chart-dot-outer" cx={cx} cy={cy} r="5" vectorEffect="non-scaling-stroke" />
                <circle className={`chart-dot tone-${s.tone}`} cx={cx} cy={cy} r="2.8" vectorEffect="non-scaling-stroke" />
              </g>
            )
          })}
        </svg>

        {/* X-axis time marks */}
        <div className="day-chart-axis" aria-hidden="true">
          <span>{times[0]}</span>
          <span>{times[24] ?? '06:00'}</span>
          <span>{times[48] ?? times[Math.floor(times.length / 2)]}</span>
          <span>{times[72] ?? '18:00'}</span>
          <span>{times.at(-1)}</span>
        </div>
      </div>

      {/* Legend with styled metric pills */}
      <footer className="day-chart-legend">
        {series.map((s) => (
          <span key={s.id} className="legend-chip">
            <i className={`tone-${s.tone}`} />
            <strong className="chip-label">{s.label}</strong>
            <small className="chip-val">{finite(s.values[step]) ? `${(s.unit === 'V' ? volts : one)(s.values[step]!)} ${s.unit}` : '—'}</small>
          </span>
        ))}
        {rules.length > 0 && (
          <span className="legend-chip rule-chip">
            <i className="rule" />
            <span className="chip-label">{rules.map((r) => r.label).join(' / ')}</span>
          </span>
        )}
      </footer>
    </section>
  )
}
