import { pct } from '../format'
import { useT } from '../i18n'
import { levelOf } from '../risk'

type Props = { p: number[]; times: string[]; watch: number; act: number }

/** P(unsafe) for each 15-minute step as bars coloured ok / watch / act, with the two threshold lines. */
export default function RiskStrip({ p, times, watch, act }: Props) {
  const t = useT()
  const peak = p.reduce((best, v, i) => (v > p[best] ? i : best), 0)
  const label = t('home.strip_label', { max: pct(p[peak] ?? 0), time: times[peak] ?? '' })
  return (
    <figure className="risk-strip">
      <svg role="img" aria-label={label} viewBox={`0 0 ${p.length} 100`} preserveAspectRatio="none">
        {p.map((v, i) => (
          <rect key={i} data-step={i} className={`step step-${levelOf(v, watch, act)}`}
            x={i + 0.1} width={0.8} y={100 - v * 100} height={Math.max(v * 100, 0.6)}>
            <title>{`${times[i]} · ${pct(v)}`}</title>
          </rect>
        ))}
        {[watch, act].map((th) => (
          <line key={th} data-threshold={th} className="threshold" x1={0} x2={p.length} y1={100 - th * 100} y2={100 - th * 100}
            vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
      <div className="strip-axis" aria-hidden="true">
        {[0, 24, 48, 72, 95].map((i) => <span key={i}>{times[i]}</span>)}
      </div>
      <figcaption className="muted">{t('home.legend', { watch: pct(watch), act: pct(act) })}</figcaption>
    </figure>
  )
}
