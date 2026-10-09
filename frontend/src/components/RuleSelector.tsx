import type { Rule } from '../api/v2types'
import { useT } from '../i18n'

/** Pick the voltage rule; shows where the rule comes from and how well that source is verified. */
export default function RuleSelector({ rules, value, onChange }: { rules: Rule[]; value: string; onChange: (id: string) => void }) {
  const t = useT()
  const current = rules.find((r) => r.id === value)
  return (
    <div className="rule-select">
      <span className="label" id="rule-label">{t('home.rule')}</span>
      <div className="segmented" role="group" aria-labelledby="rule-label">
        {rules.map((r) => (
          <button key={r.id} aria-pressed={r.id === value} className={`seg ${r.id === value ? 'active' : ''}`}
            onClick={() => onChange(r.id)}>{r.label}</button>
        ))}
      </div>
      {current && <p className="muted">{t('home.rule_source', { source: current.source, verification: current.verification })}</p>}
    </div>
  )
}
