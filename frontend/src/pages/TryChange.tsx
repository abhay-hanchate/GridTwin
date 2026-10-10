import { useMemo, useState, type CSSProperties, type ReactElement } from 'react'
import { useV2, v2Path } from '../api/v2'
import type { CatalogEntry, DaySummary, ParamSchema, Street, WhatIfResult } from '../api/v2types'
import type { Area } from '../app/areas'
import { DEFAULT_NETWORK } from '../app/defaults'
import { useView, type ViewProps } from '../app/view'
import Controls from '../components/Controls'
import Explainer, { NextStep } from '../components/Explainer'
import Prov from '../components/Prov'
import Status from '../components/Status'
import type { HomeView } from '../components/street/geometry'
import StreetMap from '../components/street/StreetMap'
import { homeClass } from '../components/street/voltage'
import VoltageCompare from '../components/VoltageCompare'
import { one, pct, volts } from '../format'
import { useT, type StringKey } from '../i18n'
import { choicesValid, chosen, initialChoices, type Choice } from '../whatif'

const NOMINAL_V = 230
const sv = { fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const ICON: Record<string, ReactElement> = {
  'change.panel_size': <svg viewBox="0 0 24 24" {...sv} aria-hidden="true"><path d="M3 18h18M5 18l2-8h10l2 8M9 10l-1 8M15 10l1 8M12 3v3M6 5l1.5 1.5M18 5l-1.5 1.5" /></svg>,
  'change.upstream_shift': <svg viewBox="0 0 24 24" {...sv} aria-hidden="true"><path d="M12 2 7 22M12 2l5 20M8.5 15h7M9.6 10h4.8M4 6h16" /></svg>,
  'change.ev_charging': <svg viewBox="0 0 24 24" {...sv} aria-hidden="true"><path d="M5 16V9l2-4h10l2 4v7M3 16h18v3H3zM7 13h2M15 13h2" /></svg>,
  'change.heatwave': <svg viewBox="0 0 24 24" {...sv} aria-hidden="true"><path d="M14 14.8V4a2 2 0 1 0-4 0v10.8a4 4 0 1 0 4 0z" /></svg>,
}
// One-click futures. Values are inputs the user can still move; the results always come from the engine.
const PRESETS: { id: string; set: Record<string, Record<string, number>> }[] = [
  { id: 'ev', set: { 'change.ev_charging': { share_of_homes: 0.5, kw: 7.4, start_hour: 19, hours: 4 } } },
  { id: 'solar', set: { 'change.panel_size': { kwp_per_home: 6 } } },
  { id: 'heat', set: { 'change.heatwave': { load_factor: 1.6 } } },
  { id: 'grid', set: { 'change.upstream_shift': { shift_pct: 3 } } },
]

const isShare = (name: string) => /share|keep/.test(name)
const stepFor = (p: ParamSchema) => {
  if (p.type === 'integer') return 1
  const lo = p.minimum ?? p.exclusiveMinimum ?? 0
  const hi = p.maximum ?? p.exclusiveMaximum ?? lo + 1
  return 10 ** Math.floor(Math.log10((hi - lo) / 100))
}
const fill = (v: number, lo: number, hi: number) => ({ '--fill': `${((v - lo) / (hi - lo || 1)) * 100}%` }) as CSSProperties

/** What if: test the street against changes before they happen, alone or with fixes, on the chosen day. */
export default function TryChange({ network = DEFAULT_NETWORK, go, ...props }: ViewProps & { go?: (area: Area) => void }) {
  const t = useT()
  const view = useView(props, 'risk')
  const catalog = useV2<CatalogEntry[]>('/catalog')
  // GRIDTWIN_OFFLINE=1 serves only precomputed results, and what-if requests are never precomputed.
  const offline = useV2<{ mode: string }>('/readiness').data?.mode === 'offline'
  return (
    <div className="v2-page">
      <header className="page-hero">
        <span className="kicker">{t('journey.step', { n: 4 })} · {t('area.try')}</span>
        <h2>{t('try.page_title')}</h2>
        <p>{t('try.page_intro')}</p>
      </header>
      <div className="usecase">
        {(['planner', 'policy', 'operator'] as const).map((k) => (
          <div key={k}><b>{t(`try.use_${k}_title` as StringKey)}</b>{t(`try.use_${k}` as StringKey)}</div>
        ))}
      </div>
      <Controls view={view} />
      <Status state={catalog} />
      {offline && <p className="note" role="note">{t('try.offline', { setting: 'GRIDTWIN_OFFLINE=0' })}</p>}
      {catalog.data && view.ready && <Builder catalog={catalog.data} network={network} rule={view.rule} date={view.date} offline={offline} />}
      <Explainer groups={['whatif', 'voltage', 'prov']} />
      <NextStep to="proof" go={go} />
    </div>
  )
}

type BuilderProps = { catalog: CatalogEntry[]; network: string; rule: string; date: string | null; offline: boolean }

function Builder({ catalog, network, rule, date, offline }: BuilderProps) {
  const t = useT()
  const [choices, setChoices] = useState<Record<string, Choice>>(() => initialChoices(catalog))
  const [submitted, setSubmitted] = useState<{ body: string; rule: string; date: string | null } | null>(null)
  const current = submitted && submitted.rule === rule && submitted.date === date ? submitted.body : null
  const result = useV2<WhatIfResult>(current ? '/whatif' : null, current ?? undefined)
  const changes = catalog.filter((e) => e.kind === 'change')
  const fixes = catalog.filter((e) => e.kind === 'fix')
  const on = Object.values(choices).filter((c) => c.on).length
  const valid = !offline && on > 0 && choicesValid(catalog, choices)
  const set = (id: string, c: Choice) => setChoices((all) => ({ ...all, [id]: c }))
  const preset = (p: (typeof PRESETS)[number]) => setChoices(() => {
    const next = initialChoices(catalog)
    for (const [id, values] of Object.entries(p.set)) {
      next[id] = { on: true, values: { ...next[id].values, ...Object.fromEntries(Object.entries(values).map(([k, v]) => [k, String(v)])) } }
    }
    return next
  })
  const run = () => valid && setSubmitted({ rule, date, body: JSON.stringify({
    network, rule, ...(date ? { date } : {}), adoption: 1, changes: chosen(catalog, choices, 'change'), fixes: chosen(catalog, choices, 'fix'),
  }) })

  return (
    <>
      <section className="card q-block" aria-labelledby="presets-title">
        <h3 id="presets-title">{t('try.presets_title')}</h3>
        <div className="segmented">
          {PRESETS.map((p) => <button key={p.id} className="seg" onClick={() => preset(p)}>{t(`try.preset_${p.id}` as StringKey)}</button>)}
          <button className="seg" onClick={() => setChoices(initialChoices(catalog))}>{t('try.reset')}</button>
        </div>
      </section>

      <section aria-labelledby="changes-title" className="q-block">
        <h3 id="changes-title">{t('try.group_change')}</h3>
        <div className="scenario-grid">
          {changes.map((e) => <Scenario key={e.id} entry={e} choice={choices[e.id]} onChange={(c) => set(e.id, c)} />)}
        </div>
      </section>

      <section aria-labelledby="fixes-title" className="q-block">
        <h3 id="fixes-title">{t('try.group_fix')}</h3>
        <div className="scenario-grid">
          {fixes.map((e) => <Scenario key={e.id} entry={e} choice={choices[e.id]} onChange={(c) => set(e.id, c)} />)}
        </div>
      </section>

      <div className="run-bar">
        <span className="muted">{on ? t('try.selected', { n: on }) : t('try.select_something')}</span>
        <button className="btn btn-light" disabled={!valid} onClick={run}>
          {t('try.run')} <span className="arrow" aria-hidden="true">▶</span>
        </button>
      </div>

      {current && <Status state={result} />}
      {result.data && <Outcome result={result.data} network={network} rule={rule} date={date} />}
    </>
  )
}

function Scenario({ entry, choice, onChange }: { entry: CatalogEntry; choice: Choice; onChange: (c: Choice) => void }) {
  const t = useT()
  const params = Object.entries(entry.params.properties ?? {})
  return (
    <div className={`scenario ${choice.on ? 'on' : ''}`} data-entry={entry.id}>
      <div className="head">
        <span className="ico">{ICON[entry.id] ?? <svg viewBox="0 0 24 24" {...sv} aria-hidden="true"><path d="M5 12l4 4 10-10" /></svg>}</span>
        <h4>{entry.label}</h4>
        <button className="switch" role="switch" aria-checked={choice.on} aria-label={entry.label} onClick={() => onChange({ ...choice, on: !choice.on })} />
      </div>
      <p>{entry.description}</p>
      {params.map(([name, p]) => {
        const lo = p.minimum ?? p.exclusiveMinimum ?? 0
        const hi = p.maximum ?? p.exclusiveMaximum ?? lo + 1
        const v = Number(choice.values[name] ?? p.default ?? lo)
        const id = `${entry.id}.${name}`
        return (
          <div key={name} className="slider-row">
            <div className="top"><label htmlFor={id}>{p.description ?? p.title ?? name}</label><b>{isShare(name) ? pct(v) : one(v)}</b></div>
            <input id={id} type="range" min={lo} max={hi} step={stepFor(p)} value={v} disabled={!choice.on} style={fill(v, lo, hi)}
              aria-valuetext={isShare(name) ? pct(v) : one(v)}
              onChange={(e) => onChange({ ...choice, values: { ...choice.values, [name]: e.target.value } })} />
          </div>
        )
      })}
      {params.length === 0 && <span className="muted">{t('try.no_params')}</span>}
    </div>
  )
}

type Row = { key: StringKey; value: (s: DaySummary) => number; fmt: (x: number) => string; lowerIsBetter: boolean }
const ROWS: Row[] = [
  { key: 'try.row_unsafe', value: (s) => s.violation_steps, fmt: String, lowerIsBetter: true },
  { key: 'try.row_peak', value: (s) => s.max_vm_pu * NOMINAL_V, fmt: volts, lowerIsBetter: true },
  { key: 'try.row_low', value: (s) => s.min_vm_pu * NOMINAL_V, fmt: volts, lowerIsBetter: false },
  { key: 'try.row_trafo', value: (s) => s.max_trafo_loading_pct, fmt: one, lowerIsBetter: true },
  { key: 'try.row_line', value: (s) => s.max_line_loading_pct, fmt: one, lowerIsBetter: true },
  { key: 'try.row_curtailed', value: (s) => s.curtailed_kwh, fmt: one, lowerIsBetter: true },
  { key: 'try.row_failed', value: (s) => s.solver_failed_steps, fmt: String, lowerIsBetter: true },
]

function Outcome({ result, network, rule, date }: { result: WhatIfResult; network: string; rule: string; date: string | null }) {
  const t = useT()
  const [side, setSide] = useState<'before' | 'after'>('after')
  // The baseline is the street as it is today; `before` (the changes without any fix) is shown when fixes were added.
  const base = result.today ?? result.before
  const withFixes = result.fixes.length > 0 && result.today !== undefined
  const street = useV2<Street>(date ? v2Path('/street', { network, rule, date, fix: 'none' }) : null)
  const peakAt = useMemo(() => {
    const run = side === 'after' ? result.after : base
    const idx = new Map(result.nodes.map((n, j) => [n, j]))
    return (node: number) => {
      const j = idx.get(node)
      const vs = j === undefined ? [] : run.node_max_v.map((row) => row[j]).filter((v): v is number => v !== null && Number.isFinite(v))
      return vs.length ? Math.max(...vs) : NaN
    }
  }, [result, side, base])
  const homes: HomeView[] = street.data ? street.data.homes.map((h, i) => {
    const v = peakAt(h.node)
    return { node: h.node, phase: street.data!.before.home_phase[i], kwp: h.kwp, cls: Number.isFinite(v) ? homeClass(v, result.limits_v) : 'v-none',
      title: t('try.map_home', { home: i + 1, v: Number.isFinite(v) ? one(v) : '' }) }
  }) : []
  return (
    <>
      <section className="card q-block" data-numbers="before and after" aria-labelledby="whatif-title">
        <h3 id="whatif-title">{t('try.result_title')} <Prov kind="modeled" /></h3>
        <p className="card-sub">{t('try.result_day', { date: result.date, min: volts(result.limits_v.min), max: volts(result.limits_v.max) })}</p>
        <div className="stats">
          {ROWS.map((r) => {
            const b = r.value(base.summary)
            const a = r.value(result.after.summary)
            const d = a - b
            const cls = Math.abs(d) < 1e-9 ? 'same' : (d < 0) === r.lowerIsBetter ? 'better' : 'worse'
            return (
              <div key={r.key} className="stat">
                <span className="label">{t(r.key)}</span>
                <span className="value">{r.fmt(a)}</span>
                <p>{t('try.was', { before: r.fmt(b) })} <span className={`delta ${cls}`}>{t(`try.delta_${cls}` as StringKey)}</span></p>
                {withFixes && <p>{t('try.changes_alone', { value: r.fmt(r.value(result.before.summary)) })}</p>}
              </div>
            )
          })}
        </div>
      </section>
      {result.after.summary.solver_failed_steps > 0 && (
        <p className="note" role="note">{t('try.nosolve', { n: result.after.summary.solver_failed_steps })}</p>
      )}
      <VoltageCompare voltage={{ t: result.t, before_max_v: base.max_v, after_max_v: result.after.max_v }}
        label={t('try.chart_name')} vmax={result.limits_v.max} />
      {street.data && (
        <section className="card q-block" aria-labelledby="whatif-map-title">
          <h3 id="whatif-map-title">{t('try.map_title')} <Prov kind="modeled" /></h3>
          <div className="segmented" role="group">
            <button className="seg" aria-pressed={side === 'before'} onClick={() => setSide('before')}>{t('try.map_before')}</button>
            <button className="seg" aria-pressed={side === 'after'} onClick={() => setSide('after')}>{t('try.map_after')}</button>
          </div>
          <div className="street-scroll">
            <StreetMap layout={street.data.layout} homes={homes} trafoLabel={t('player.trafo', { kva: Math.round(street.data.trafo_kva) })}
              trafoSub={t('player.trafo_sub')} label={t('try.map_label')} />
          </div>
        </section>
      )}
    </>
  )
}
