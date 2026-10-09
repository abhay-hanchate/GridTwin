import type { Risk } from '../api/v2types'
import { useT, type StringKey } from '../i18n'
import { dominantLimit } from '../risk'

/** The one-line answer at the top of Home, for example "Tomorrow: ACT, over-voltage likely between 11:30 and 13:45". */
export default function Verdict({ risk, times, act }: { risk: Risk; times: string[]; act: number }) {
  const t = useT()
  const level = t(`level.${risk.level}` as StringKey)
  const limit = t(`limit.${dominantLimit(risk.shares)}` as StringKey)
  let text: string
  if (risk.level === 'act' && risk.first_act) {
    const last = risk.p_unsafe.reduce((end, p, i) => (p >= act ? i : end), -1)
    text = t('home.headline.act', { level, limit, from: risk.first_act, to: times[last] ?? risk.first_act })
  } else if (risk.level !== 'ok' && risk.first_watch) {
    text = t('home.headline.watch', { level, limit, from: risk.first_watch })
  } else {
    text = t('home.headline.ok', { level })
  }
  return <h2 className={`verdict verdict-${risk.level}`}>{text}</h2>
}
