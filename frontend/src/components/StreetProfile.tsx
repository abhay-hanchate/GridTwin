import type { WhatIfResult } from '../api/v2types'
import { useT } from '../i18n'
import Prov from './Prov'

const W = 100
const H = 100

/** The highest voltage over the day at every point of the street, before and after, with the rule's upper limit. */
export default function StreetProfile({ result }: { result: WhatIfResult }) {
  const t = useT()
  const peak = (rows: number[][]) => result.nodes.map((_, j) => Math.max(...rows.map((row) => row[j])))
  const before = peak(result.before.node_max_v)
  const after = peak(result.after.node_max_v)
  const vmax = result.limits_v.max
  const all = [...before, ...after, vmax]
  const lo = Math.floor(Math.min(...all) - 2)
  const hi = Math.ceil(Math.max(...all) + 2)
  const y = (v: number) => H - ((v - lo) / (hi - lo)) * H
  const points = (vs: number[]) => vs.map((v, i) => `${((i + 0.5) * W) / vs.length},${y(v).toFixed(2)}`).join(' ')
  return (
    <section className="card" data-numbers="street profile">
      <h3>{t('try.profile_title')} <Prov kind="modeled" /></h3>
      <svg className="volt-compare" role="img" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
        aria-label={t('try.profile_label', { n: result.nodes.length, vmax: Math.round(vmax) })}>
        <line className="rule-line" x1={0} x2={W} y1={y(vmax)} y2={y(vmax)} vectorEffect="non-scaling-stroke" />
        <polyline data-series="before" className="series-before" points={points(before)} vectorEffect="non-scaling-stroke" />
        <polyline data-series="after" className="series-after" points={points(after)} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="strip-axis" aria-hidden="true"><span>{t('try.profile_start')}</span><span>{t('try.profile_end')}</span></div>
      <p className="legend-row muted">
        <span><i className="key key-before" />{t('fixes.before')}</span>
        <span><i className="key key-after" />{t('fixes.after')}</span>
        <span><i className="key key-rule" />{t('fixes.rule_line')} {Math.round(vmax)} V</span>
      </p>
    </section>
  )
}
