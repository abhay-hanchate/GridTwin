import { CalendarDays, Gauge } from 'lucide-react'
import { useV2, v2Path } from '../api/v2'
import type { Risk } from '../api/v2types'
import { DEFAULT_NETWORK } from '../app/defaults'
import { useView } from '../app/view'
import { dayName } from '../day'
import { useLang, useT, type StringKey } from '../i18n'

/** A thin bar under the header: the day, the rule and the day's status, always in view while scrolling.
 *  It reads the same cached /risk result the pages use, so it adds no computation. */
export default function ContextBar({ rule, date }: { rule: string; date: string | null }) {
  const t = useT()
  const { lang } = useLang()
  const view = useView({ rule, date })
  const risk = useV2<Risk>(view.ready && view.date ? v2Path('/risk', { network: DEFAULT_NETWORK, rule: view.rule, date: view.date }) : null)
  if (!view.date) return null
  const level = risk.data?.level
  return (
    <div className="context-bar" aria-label={t('ctx.bar')}>
      <span className="cb-item"><CalendarDays size={15} aria-hidden="true" />{dayName(view.date, lang, t)}</span>
      <span className="cb-sep" aria-hidden="true" />
      <span className="cb-item"><Gauge size={15} aria-hidden="true" />{(view.band?.label ?? view.rule).split(':').pop()?.trim()}</span>
      <span className={`cb-pill lvl-${level ?? 'pending'}`}>
        <span className="cb-dot" aria-hidden="true" />
        {level ? t(`level.${level}` as StringKey) : '…'}
        {risk.data && level !== 'ok' && <span className="cb-hours">{t('ctx.bar_hours', { hours: risk.data.expected_unsafe_hours.mean.toFixed(1) })}</span>}
      </span>
    </div>
  )
}
