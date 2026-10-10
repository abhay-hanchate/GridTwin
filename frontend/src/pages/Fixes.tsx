import { useRef, useState, type ReactElement } from 'react'
import { useV2, v2Path } from '../api/v2'
import type { Fixes as FixesResult, Outcome, Verdict } from '../api/v2types'
import type { Area } from '../app/areas'
import { DEFAULT_NETWORK } from '../app/defaults'
import { useView, type ViewProps } from '../app/view'
import Controls from '../components/Controls'
import Envelope from '../components/Envelope'
import { NextStep } from '../components/Explainer'
import PhasePlan from '../components/PhasePlan'
import Prov from '../components/Prov'
import Status from '../components/Status'
import StreetPlayer from '../components/street/StreetPlayer'
import VoltageCompare from '../components/VoltageCompare'
import { bindingText } from '../fixes'
import { one } from '../format'
import { useT, type StringKey } from '../i18n'

const KINDS = ['tap', 'inverter', 'combined', 'curtailment', 'envelope', 'phase', 'battery', 'switching'] as const
type Kind = (typeof KINDS)[number]
const kindOf = (k: string): Kind => ((KINDS as readonly string[]).includes(k) ? (k as Kind) : 'combined')

const s = { fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const ICON: Record<Kind, ReactElement> = {
  tap: <svg viewBox="0 0 24 24" {...s} aria-hidden="true"><circle cx="12" cy="12" r="8" /><path d="M12 12l4-4M12 4v2M20 12h-2" /></svg>,
  inverter: <svg viewBox="0 0 24 24" {...s} aria-hidden="true"><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M8 12c1-2 2-2 3 0s2 2 3 0 2-2 3 0" /></svg>,
  combined: <svg viewBox="0 0 24 24" {...s} aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>,
  curtailment: <svg viewBox="0 0 24 24" {...s} aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M4 20 20 4" /></svg>,
  envelope: <svg viewBox="0 0 24 24" {...s} aria-hidden="true"><path d="M3 12h4l2-6 4 12 2-6h6" /></svg>,
  phase: <svg viewBox="0 0 24 24" {...s} aria-hidden="true"><path d="M4 7h12l-3-3M20 17H8l3 3" /></svg>,
  battery: <svg viewBox="0 0 24 24" {...s} aria-hidden="true"><rect x="3" y="7" width="16" height="10" rx="2" /><path d="M21 11v2M7 10v4M11 10v4" /></svg>,
  switching: <svg viewBox="0 0 24 24" {...s} aria-hidden="true"><circle cx="5" cy="12" r="2" /><circle cx="19" cy="12" r="2" /><path d="M7 12l9-5" /></svg>,
}

/** Fixes: every option the physics tested for the day, ranked; click one to see what it does and watch it work. */
export default function Fixes({ network = DEFAULT_NETWORK, go, ...props }: ViewProps & { go?: (area: Area) => void }) {
  const t = useT()
  const view = useView(props, 'fixes')
  const fixes = useV2<FixesResult>(view.ready && view.date ? v2Path('/fixes', { network, rule: view.rule, date: view.date }) : null)
  return (
    <div className="v2-page">
      <header className="page-hero">
        <span className="kicker">{t('journey.step', { n: 2 })} · {t('area.fixes')}</span>
        <h2>{t('fixes.page_title')}</h2>
        <p>{t('fixes.page_intro')}</p>
      </header>
      <Controls view={view} />
      <Status state={fixes} />
      {fixes.data && <FixesView key={`${fixes.data.date}-${fixes.data.rule}`} result={fixes.data} vmax={view.band?.vmax_v}
        network={network} rule={view.rule} date={view.date} />}
      <NextStep to="planning" go={go} />
    </div>
  )
}

/** Safe fixes first in their rank order, then the rest by how many unsafe quarter hours they leave. */
const ordered = (outcomes: Outcome[]) => [...outcomes].sort((a, b) =>
  (a.safe === b.safe ? 0 : a.safe ? -1 : 1) || (a.rank ?? 99) - (b.rank ?? 99) || a.unsafe_steps - b.unsafe_steps)

function FixesView({ result, vmax, network, rule, date }: { result: FixesResult; vmax?: number; network: string; rule: string; date: string | null }) {
  const t = useT()
  const v = result.verdict
  const byId = new Map(result.outcomes.map((o) => [o.id, o]))
  const focusId = (v.safe_action_found ? v.recommended : v.closest) ?? result.outcomes[0]?.id ?? null
  const [chosen, setChosen] = useState<string | null>(focusId)
  const detailRef = useRef<HTMLElement>(null)
  const pick = (id: string) => { setChosen(id); setTimeout(() => detailRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }), 0) }
  const selected = chosen ? byId.get(chosen) : undefined
  const baseline = v.baseline_unsafe_steps ?? result.baseline_unsafe_steps
  return (
    <>
      {v.safe_action_found && focusId ? <Recommended outcome={byId.get(focusId)!} baseline={baseline} onOpen={() => pick(focusId)} />
        : <NoSafeAction verdict={v} closest={focusId ? byId.get(focusId) : undefined} />}

      <section className="card" aria-labelledby="tested-title">
        <h3 id="tested-title">{t('fixes.tested_title', { n: result.outcomes.length })} <Prov kind="modeled" /></h3>
        <p className="card-sub">{t('fixes.tested_intro', { steps: baseline })}</p>
        <div className="fix-grid">
          {ordered(result.outcomes).map((o) => (
            <button key={o.id} className="fix-tile" aria-pressed={chosen === o.id} onClick={() => pick(o.id)} data-fix={o.id}>
              <span className="top">
                <span className="kind">{ICON[kindOf(o.kind)]}{t(`fixguide.${kindOf(o.kind)}.name` as StringKey)}</span>
                {o.rank !== null && o.safe ? <span className="rank">{t('fixes.rank', { rank: o.rank })}</span> : null}
              </span>
              <h4>{o.label}</h4>
              <span className="meta">
                <span className={`chip ${o.safe ? 'ok' : 'act'}`}>{t(o.safe ? 'fixes.tile_safe' : 'fixes.tile_unsafe', { steps: o.unsafe_steps })}</span>
                {o.cost.curtailed_kwh > 0 && <span className="chip sun">{t('fixes.tile_curtailed', { kwh: one(o.cost.curtailed_kwh) })}</span>}
                {o.cost.operations > 0 && <span className="chip">{t('fixes.tile_ops', { n: o.cost.operations })}</span>}
              </span>
            </button>
          ))}
        </div>
      </section>

      {selected && (
        <section ref={detailRef} className="card fix-detail" aria-labelledby="detail-title" data-numbers="fix detail">
          <FixDetail outcome={selected} baseline={baseline} network={network} rule={rule} date={date} />
          {selected.id === focusId && selected.details?.phase_moves && <PhasePlan moves={selected.details.phase_moves} />}
          {selected.id === focusId && selected.details?.export_limits && <Envelope limits={selected.details.export_limits} />}
          {selected.id === focusId && selected.details?.voltage && <VoltageCompare voltage={selected.details.voltage} label={selected.label} vmax={vmax} />}
        </section>
      )}

      <details className="more">
        <summary>{t('fixes.compare_title')}</summary>
        <CompareTable outcomes={result.outcomes} />
      </details>
    </>
  )
}

function Recommended({ outcome, baseline, onOpen }: { outcome: Outcome; baseline: number; onOpen: () => void }) {
  const t = useT()
  return (
    <section className="verdict-box lvl-ok" aria-labelledby="rec-title" data-recommended data-numbers="recommended fix">
      <span className="badge">{t('fixes.recommended')}</span>
      <h2 id="rec-title" className="verdict verdict-ok">{outcome.label}</h2>
      <p className="cause">{t('fixes.rec_line', { before: baseline, after: outcome.unsafe_steps, margin: one(outcome.cost.margin_v) })}</p>
      <div><button className="btn btn-primary" onClick={onOpen}>{t('fixes.watch_it')} <span className="arrow" aria-hidden="true">▶</span></button></div>
    </section>
  )
}

function NoSafeAction({ verdict, closest }: { verdict: Verdict; closest?: Outcome }) {
  const t = useT()
  return (
    <section className="verdict-box lvl-act no-safe" aria-labelledby="no-safe-title" data-numbers="no safe action">
      <h2 id="no-safe-title" className="verdict verdict-act"><span className="level-pill lvl-act">{t('fixes.none_pill')}</span>{t('fixes.none_title')}</h2>
      <p className="cause">{t('fixes.none_body')} <Prov kind="modeled" /></p>
      {verdict.binding_limit && <p className="cause">{bindingText(t, verdict.binding_limit)}</p>}
      {closest && <p className="cause">{t('fixes.closest', { label: closest.label, steps: closest.unsafe_steps })}</p>}
      {verdict.still_needs && <p className="cause">{t('fixes.still_needs', { text: verdict.still_needs })}</p>}
    </section>
  )
}

function FixDetail({ outcome, baseline, network, rule, date }: { outcome: Outcome; baseline: number; network: string; rule: string; date: string | null }) {
  const t = useT()
  const kind = kindOf(outcome.kind)
  const delta = baseline - outcome.unsafe_steps
  return (
    <>
      <div className="fix-head">
        <h3 id="detail-title">{ICON[kind]} {outcome.label}</h3>
        <span className={`chip ${outcome.safe ? 'ok' : 'act'}`}>{t(outcome.safe ? 'fixes.detail_safe' : 'fixes.detail_unsafe')}</span>
      </div>
      <div className="explain">
        {(['what', 'how', 'who', 'tradeoff'] as const).map((k) => (
          <div key={k}><h4>{t(`fixes.q_${k}`)}</h4><p>{t(`fixguide.${kind}.${k}` as StringKey)}</p></div>
        ))}
      </div>
      <div className="stats">
        <div className={`stat ${outcome.unsafe_steps === 0 ? 'ok' : 'act'}`}>
          <span className="label">{t('fixes.d_unsafe')}</span>
          <span className="value">{outcome.unsafe_steps}<small>{t('fixes.d_of', { before: baseline })}</small></span>
          <p>{delta > 0 ? t('fixes.d_removed', { n: delta }) : t('fixes.d_none_removed')}</p>
        </div>
        <div className="stat">
          <span className="label">{t('fixes.d_margin')}</span>
          <span className="value">{one(outcome.cost.margin_v)}<small>V</small></span>
          <p>{t('fixes.d_margin_note')}</p>
        </div>
        <div className="stat">
          <span className="label">{t('fixes.d_curtailed')}</span>
          <span className="value">{one(outcome.cost.curtailed_kwh)}<small>kWh</small></span>
          <p>{t('fixes.d_curtailed_note')}</p>
        </div>
        <div className="stat">
          <span className="label">{t('fixes.d_ops')}</span>
          <span className="value">{outcome.cost.operations}</span>
          <p>{t('fixes.d_ops_note')}</p>
        </div>
      </div>
      {outcome.binding_limit && <p className="note">{bindingText(t, outcome.binding_limit)}</p>}
      <div>
        <h3>{t('fixes.watch_title')}</h3>
        <p className="card-sub">{t('fixes.watch_intro')}</p>
        <StreetPlayer network={network} rule={rule} date={date} fix={outcome.id} fixLabel={outcome.label} />
      </div>
    </>
  )
}

function CompareTable({ outcomes }: { outcomes: Outcome[] }) {
  const t = useT()
  return (
    <div className="table-scroll" data-numbers="all options">
      <table className="data-table" aria-label={t('fixes.compare_title')}>
        <thead>
          <tr>
            {(['col_option', 'col_safe', 'col_unsafe', 'col_curtailed', 'col_operations', 'col_margin', 'col_limit'] as const)
              .map((k) => <th key={k} scope="col">{t(`fixes.${k}`)}</th>)}
          </tr>
        </thead>
        <tbody>
          {outcomes.map((o) => (
            <tr key={o.id} className={o.safe ? 'row-safe' : 'row-unsafe'}>
              <th scope="row">{o.label}</th>
              <td>{t(o.safe ? 'fixes.yes' : 'fixes.no')}</td>
              <td>{o.unsafe_steps}</td>
              <td>{one(o.cost.curtailed_kwh)}</td>
              <td>{o.cost.operations}</td>
              <td>{one(o.cost.margin_v)}</td>
              <td>{o.binding_limit ? t(`limit.${o.binding_limit.type}` as StringKey) : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Prov kind="modeled" />
    </div>
  )
}

