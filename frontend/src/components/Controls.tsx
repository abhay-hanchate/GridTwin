import type { View } from '../app/view'
import DaySelector from './DaySelector'
import RuleSelector from './RuleSelector'
import Status from './Status'

/** The rule and day pickers at the top of a page. */
export default function Controls({ view }: { view: View; answered?: string }) {
  return (
    <div className="controls">
      {view.rules.data ? <RuleSelector rules={view.rules.data} value={view.rule} onChange={view.setRule} /> : <Status state={view.rules} />}
      <DaySelector calendar={view.calendar} value={view.date} onChange={view.setDate} />
    </div>
  )
}
