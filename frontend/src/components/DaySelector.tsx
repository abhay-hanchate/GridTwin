import type { Calendar } from '../api/v2types'
import { useT } from '../i18n'

/** Pick the day: the real tomorrow in one click, or any day of the forecast archive from the calendar.
 *  Offline (GRIDTWIN_OFFLINE=1) only the days that were computed can be shown, so only those are offered. */
export default function DaySelector({ calendar, value, onChange }: { calendar: Calendar | null; value: string | null; onChange: (date: string) => void }) {
  const t = useT()
  if (!calendar) return null
  const isTomorrow = value === calendar.tomorrow
  if (calendar.offline) {
    return (
      <div className="rule-select">
        <span className="label" id="day-label">{t('day.label')}</span>
        <div className="date-pick" role="group" aria-labelledby="day-label">
          {calendar.ready.map((d) => (
            <button key={d} className="seg" aria-pressed={d === value} onClick={() => onChange(d)}>{d}</button>
          ))}
          <p className="hint muted">{t('day.offline')}</p>
        </div>
      </div>
    )
  }
  return (
    <div className="rule-select">
      <span className="label" id="day-label">{t('day.label')}</span>
      <div className="date-pick" role="group" aria-labelledby="day-label">
        <button className="seg" aria-pressed={isTomorrow} onClick={() => onChange(calendar.tomorrow)}>{t('day.tomorrow')}</button>
        <label className="sr-only" htmlFor="day-input">{t('day.pick')}</label>
        <input id="day-input" type="date" className={isTomorrow ? '' : 'active'} min={calendar.archive.first} max={calendar.archive.last}
          value={!isTomorrow && value ? value : ''} onChange={(e) => e.target.value && onChange(e.target.value)} />
        <p className="hint muted">{isTomorrow ? t('day.live_hint') : t('day.archive_hint', { first: calendar.archive.first, last: calendar.archive.last })}</p>
      </div>
    </div>
  )
}
