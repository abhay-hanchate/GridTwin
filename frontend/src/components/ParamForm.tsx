import type { CatalogEntry } from '../api/v2types'
import { useT } from '../i18n'
import { paramProblem, type Choice, type ParamProblem } from '../whatif'

type T = ReturnType<typeof useT>

function problemText(t: T, p: ParamProblem): string {
  switch (p.kind) {
    case 'number': return t('try.error_number')
    case 'integer': return t('try.error_integer')
    case 'range': return t('try.error_range', { min: p.min, max: p.max })
    case 'above': return t('try.error_above', { min: p.min })
    case 'below': return t('try.error_below', { max: p.max })
  }
}

/** One catalog entry: a switch to include it, and one input per parameter built from its JSON schema. */
export default function ParamForm({ entry, choice, onChange }: { entry: CatalogEntry; choice: Choice; onChange: (c: Choice) => void }) {
  const t = useT()
  const params = Object.entries(entry.params.properties ?? {})
  return (
    <fieldset className={`param-entry ${choice.on ? 'on' : ''}`}>
      <legend>{entry.label}</legend>
      <label className="include">
        <input type="checkbox" checked={choice.on} onChange={(e) => onChange({ ...choice, on: e.target.checked })} />
        {t('try.include')}
      </label>
      <p className="muted">{entry.description}</p>
      {params.map(([name, schema]) => {
        const id = `${entry.id}.${name}`
        const raw = choice.values[name] ?? ''
        const problem = choice.on ? paramProblem(schema, raw) : null
        const min = schema.minimum ?? schema.exclusiveMinimum
        const max = schema.maximum ?? schema.exclusiveMaximum
        return (
          <div key={name} className="param">
            <label htmlFor={id}>{schema.description ?? schema.title ?? name}</label>
            <input id={id} type="number" inputMode="decimal" value={raw} disabled={!choice.on}
              min={min} max={max} step={schema.type === 'integer' ? 1 : 'any'}
              aria-invalid={problem !== null} aria-describedby={problem ? `${id}-error` : undefined}
              onChange={(e) => onChange({ ...choice, values: { ...choice.values, [name]: e.target.value } })} />
            {problem && <span id={`${id}-error`} className="error" role="alert">{problemText(t, problem)}</span>}
          </div>
        )
      })}
    </fieldset>
  )
}
