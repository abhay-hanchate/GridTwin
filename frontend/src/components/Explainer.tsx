import type { ReactNode } from 'react'
import type { Area } from '../app/areas'
import { useT, type StringKey } from '../i18n'

/** Every label a page uses, explained in one place at the end of the page. Groups are shared between pages so the
 *  same word always gets the same explanation. */
export type Group = 'levels' | 'cause' | 'voltage' | 'phases' | 'prov' | 'range' | 'fix' | 'decision' | 'whatif'

const dot = (color: string, square = false): ReactNode => (
  <span className="dot" style={{ background: color, borderRadius: square ? 3 : undefined }} />
)
const line = (color: string, dashed = false): ReactNode => (
  <span style={{ width: 20, borderTop: `3px ${dashed ? 'dashed' : 'solid'} ${color}`, borderRadius: 2 }} />
)

const GROUPS: Record<Group, { key: string; mark: ReactNode }[]> = {
  levels: [{ key: 'ok', mark: dot('var(--ok)') }, { key: 'watch', mark: dot('var(--watch)') }, { key: 'act', mark: dot('var(--act)') }],
  cause: [{ key: 'solar', mark: dot('var(--sun)', true) }, { key: 'grid', mark: dot('var(--grid)', true) }],
  voltage: [{ key: 'v_ok', mark: dot('var(--ok)') }, { key: 'v_near', mark: dot('var(--watch)') }, { key: 'v_over', mark: dot('var(--act)') },
    { key: 'v_under', mark: dot('var(--under)') }],
  phases: [{ key: 'ph_abc', mark: <span style={{ display: 'grid', gap: 2 }}>{line('var(--ph-a)')}{line('var(--ph-b)')}{line('var(--ph-c)')}</span> },
    { key: 'ph_n', mark: line('var(--ph-n)', true) }, { key: 'ph_flow', mark: <span aria-hidden="true">⇢</span> }],
  prov: [{ key: 'observed', mark: <span className="prov prov-observed">·</span> }, { key: 'modeled', mark: <span className="prov">·</span> },
    { key: 'benchmark', mark: <span className="prov prov-benchmark">·</span> }],
  range: [{ key: 'p10p90', mark: <span aria-hidden="true">↔</span> }, { key: 'design_day', mark: <span aria-hidden="true">☀</span> }],
  fix: [{ key: 'safe', mark: dot('var(--ok)') }, { key: 'unsafe_fix', mark: dot('var(--act)') }, { key: 'recommended', mark: <span className="badge">✓</span> },
    { key: 'no_safe', mark: dot('var(--act)', true) }, { key: 'binding', mark: <span aria-hidden="true">⛔</span> }],
  decision: [{ key: 'approve', mark: dot('var(--ok)') }, { key: 'conditions', mark: dot('var(--watch)') }, { key: 'refuse', mark: dot('var(--act)') },
    { key: 'headroom', mark: <span aria-hidden="true">▤</span> }],
  whatif: [{ key: 'before_after', mark: <span aria-hidden="true">⇄</span> }, { key: 'better_worse', mark: <span className="delta better">↓</span> }],
}

export default function Explainer({ groups }: { groups: Group[] }) {
  const t = useT()
  return (
    <section className="explainer" aria-labelledby="explainer-title">
      <h2 id="explainer-title">{t('explain.title')}</h2>
      <p>{t('explain.intro')}</p>
      {groups.map((g) => (
        <div key={g} className="explain-group">
          <h3>{t(`explain.group.${g}` as StringKey)}</h3>
          <dl className="explain-grid">
            {GROUPS[g].map((item) => (
              <div key={item.key}>
                <span className="mark" aria-hidden="true">{item.mark}</span>
                <dt>{t(`explain.${item.key}` as StringKey)}</dt>
                <dd>{t(`explain.${item.key}_text` as StringKey)}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </section>
  )
}

/** The way through the project: each page ends by pointing to the next question. */
export function NextStep({ to, go }: { to: Area; go?: (area: Area) => void }) {
  const t = useT()
  return (
    <section className="next-step">
      <p>{t(`next.${to}` as StringKey)}<span>{t(`next.${to}_why` as StringKey)}</span></p>
      <button className="btn btn-primary" onClick={() => { go?.(to); if (typeof window.scrollTo === 'function') try { window.scrollTo({ top: 0 }) } catch { /* jsdom */ } }}>
        {t(`area.${to}` as StringKey)} <span className="arrow" aria-hidden="true">→</span>
      </button>
    </section>
  )
}
