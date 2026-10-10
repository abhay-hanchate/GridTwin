import { pct } from '../format'
import { useT } from '../i18n'
import { levelOf, type CauseSplit } from '../risk'

type Props = { p: number[]; times: string[]; watch: number; act: number; split?: CauseSplit }

/** P(unsafe) for each 15-minute step. With the solar-off run, each bar is split: the grid's own part (still unsafe
 *  with every panel off) at the bottom, what rooftop solar adds on top. The dashed lines are watch and act. */
export default function RiskStrip({ p, times, watch, act, split }: Props) {
  const t = useT()
  const peak = p.reduce((best, v, i) => (v > p[best] ? i : best), 0)
  const label = t('home.strip_label', { max: pct(p[peak] ?? 0), time: times[peak] ?? '' })
  const attributed = split !== undefined && split.solarShare !== null
  return (
    <figure className="risk-strip">
      <svg role="img" aria-label={label} viewBox={`0 0 ${p.length} 100`} preserveAspectRatio="none">
        {p.map((v, i) => {
          const grid = attributed ? split.grid[i] : 0
          return (
            <g key={i} data-step={i} className={`step step-${levelOf(v, watch, act)}`}>
              <title>{attributed
                ? t('home.strip_step', { time: times[i], total: pct(v), grid: pct(grid), solar: pct(v - grid) })
                : `${times[i]} · ${pct(v)}`}</title>
              {grid > 0 && <rect className="part-grid" x={i + 0.12} width={0.76} y={100 - grid * 100} height={grid * 100} />}
              <rect className="part-solar" x={i + 0.12} width={0.76} y={100 - v * 100} height={Math.max((v - grid) * 100, v > 0 ? 0.6 : 0)} />
            </g>
          )
        })}
        {[watch, act].map((th) => (
          <line key={th} data-threshold={th} className="threshold" x1={0} x2={p.length} y1={100 - th * 100} y2={100 - th * 100}
            vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
      <div className="strip-axis" aria-hidden="true">
        {[0, 24, 48, 72, 95].map((i) => <span key={i}>{times[i]}</span>)}
      </div>
      <figcaption>
        <ul className="strip-legend">
          {attributed && <li><span className="swatch sun" />{t('home.key_solar')}</li>}
          {attributed && <li><span className="swatch grid" />{t('home.key_grid')}</li>}
          <li><span className="swatch line" />{t('home.legend', { watch: pct(watch), act: pct(act) })}</li>
        </ul>
      </figcaption>
    </figure>
  )
}
