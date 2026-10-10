import type { Risk } from '../api/v2types'
import { dayName } from '../day'
import { useLang, useT, type StringKey } from '../i18n'
import { causeSplit, dominantLimit } from '../risk'

/** The one-line answer, for example "15 May 2025: ACT, over-voltage likely between 06:15 and 14:30", and below it
 *  what causes it: rooftop solar, or the grid's own voltage (still unsafe with every panel off). */
export default function Verdict({ risk, times, act }: { risk: Risk; times: string[]; act: number }) {
  const t = useT()
  const { lang } = useLang()
  const level = t(`level.${risk.level}` as StringKey)
  const limit = t(`limit.${dominantLimit(risk.shares)}` as StringKey)
  const day = dayName(risk.date, lang, t)
  let text: string
  if (risk.level === 'act' && risk.first_act) {
    const last = risk.p_unsafe.reduce((end, p, i) => (p >= act ? i : end), -1)
    text = t('home.headline.act', { day, level, limit, from: risk.first_act, to: times[last] ?? risk.first_act })
  } else if (risk.level !== 'ok' && risk.first_watch) {
    text = t('home.headline.watch', { day, level, limit, from: risk.first_watch })
  } else {
    text = t('home.headline.ok', { day, level })
  }
  const share = risk.level === 'ok' ? null : causeSplit(risk).solarShare
  return (
    <div className={`verdict-box lvl-${risk.level}`}>
      <h2 className={`verdict verdict-${risk.level}`}>
        <span className={`level-pill lvl-${risk.level}`}>{level}</span> {text}
      </h2>
      {share !== null && (
        <p className="cause">
          {share >= 0.5
            ? <><b className="sun">{t('home.cause_solar_lead')}</b> {t('home.cause_solar', { share: `${Math.round(share * 100)}%` })}</>
            : <><b className="grid">{t('home.cause_grid_lead')}</b> {t('home.cause_grid', { share: `${Math.round((1 - share) * 100)}%` })}</>}
        </p>
      )}
    </div>
  )
}
