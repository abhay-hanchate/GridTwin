import type { OutcomeDetails } from '../api/v2types'
import { useT } from '../i18n'
import Prov from './Prov'

type Props = { voltage: NonNullable<OutcomeDetails['voltage']>; label: string; vmax?: number }
const W = 96
const H = 100

/** Highest street voltage per quarter hour before and after a fix, with the rule's upper limit. */
export default function VoltageCompare({ voltage, label, vmax }: Props) {
  const t = useT()
  const all = [...voltage.before_max_v, ...voltage.after_max_v, ...(vmax ? [vmax] : [])]
  const lo = Math.floor(Math.min(...all) - 2)
  const hi = Math.ceil(Math.max(...all) + 2)
  const y = (v: number) => H - ((v - lo) / (hi - lo)) * H
  const points = (vs: number[]) => vs.map((v, i) => `${((i + 0.5) * W) / vs.length},${y(v).toFixed(2)}`).join(' ')
  const name = t('fixes.chart_label', { label, vmax: vmax ?? '' })
  return (
    <section className="card" data-numbers="voltage before and after">
      <h3>{t('fixes.chart_title')} <Prov kind="modeled" /></h3>
      <svg className="volt-compare" role="img" aria-label={name} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        {vmax !== undefined && <line className="rule-line" x1={0} x2={W} y1={y(vmax)} y2={y(vmax)} vectorEffect="non-scaling-stroke" />}
        <polyline data-series="before" className="series-before" points={points(voltage.before_max_v)} vectorEffect="non-scaling-stroke" />
        <polyline data-series="after" className="series-after" points={points(voltage.after_max_v)} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="strip-axis" aria-hidden="true">
        <span>{voltage.t[0]}</span><span>{voltage.t[48]}</span><span>{voltage.t[voltage.t.length - 1]}</span>
      </div>
      <p className="legend-row muted">
        <span><i className="key key-before" />{t('fixes.before')}</span>
        <span><i className="key key-after" />{t('fixes.after')}</span>
        {vmax !== undefined && <span><i className="key key-rule" />{t('fixes.rule_line')} {Math.round(vmax)} V</span>}
      </p>
    </section>
  )
}
