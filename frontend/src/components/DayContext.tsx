import { CalendarDays } from 'lucide-react'
import { useState } from 'react'
import type { View } from '../app/view'
import { dayName } from '../day'
import { useLang, useT } from '../i18n'
import Controls from './Controls'

/** The day and rule this page answers for, carried over from Tomorrow, so nothing has to be picked again.
 *  The pickers are still one click away. */
export default function DayContext({ view }: { view: View }) {
  const t = useT()
  const { lang } = useLang()
  const [open, setOpen] = useState(false)
  if (!view.date) return <Controls view={view} />
  return (
    <div className="day-context" data-day={view.date}>
      <div className="dc-line">
        <CalendarDays size={18} aria-hidden="true" />
        <p>
          <b>{t('ctx.line', { day: dayName(view.date, lang, t), rule: view.band?.label ?? view.rule })}</b>
          <span className="muted">{t('ctx.same')}</span>
        </p>
        <button className="btn btn-ghost dc-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {t(open ? 'ctx.done' : 'ctx.change')}
        </button>
      </div>
      {open && <Controls view={view} />}
    </div>
  )
}
