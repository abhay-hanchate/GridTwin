import type { DemoDay } from '../app/view'
import { useT, type StringKey } from '../i18n'

/** Pick which precomputed day to look at. `value` is the day the API answered for. */
export default function DaySelector({ days, value, onChange }: { days: DemoDay[]; value?: string; onChange: (date: string) => void }) {
  const t = useT()
  if (days.length === 0) return null
  return (
    <div className="rule-select">
      <span className="label" id="day-label">{t('day.label')}</span>
      <div className="segmented" role="group" aria-labelledby="day-label">
        {days.map((d) => (
          <button key={d.date} aria-pressed={d.date === value} className={`seg ${d.date === value ? 'active' : ''}`}
            onClick={() => onChange(d.date)}>
            {t(`day.${d.dayType}` as StringKey)} · {d.date}
          </button>
        ))}
      </div>
    </div>
  )
}
