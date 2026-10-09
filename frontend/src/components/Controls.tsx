import type { View } from '../app/view'
import DaySelector from './DaySelector'
import RuleSelector from './RuleSelector'
import Status from './Status'

/** The rule and day pickers at the top of a page. `answered` is the date the API actually used. */
export default function Controls({ view, answered }: { view: View; answered?: string }) {
  return (
    <>
      {view.rules.data ? <RuleSelector rules={view.rules.data} value={view.rule} onChange={view.setRule} /> : <Status state={view.rules} />}
      <DaySelector days={view.days} value={view.date ?? answered} onChange={view.setDate} />
    </>
  )
}
