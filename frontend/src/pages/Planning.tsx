import { useMemo, useState, type ReactNode } from 'react'
import { useV2, v2Path } from '../api/v2'
import type { Headroom, Hosting, MeterSites, RxMap, Street, Transformers } from '../api/v2types'
import type { Area } from '../app/areas'
import { DEFAULT_NETWORK } from '../app/defaults'
import { useView, type ViewProps } from '../app/view'
import ConnectionPanel from '../components/ConnectionPanel'
import Controls from '../components/Controls'
import Explainer, { NextStep } from '../components/Explainer'
import Prov from '../components/Prov'
import Status from '../components/Status'
import type { HomeView, Marker } from '../components/street/geometry'
import StreetMap from '../components/street/StreetMap'
import { bindingText } from '../fixes'
import { one, pct } from '../format'
import { useT, type StringKey } from '../i18n'

type Layer = 'headroom' | 'connect' | 'meters'
const LAYERS: Layer[] = ['headroom', 'connect', 'meters']
const METERS_SHOWN = 5

/** Planning (E1-E4, E6, P7.7) as four questions a planner asks, with the street map as the place to point at. */
export default function Planning({ network = DEFAULT_NETWORK, go, ...props }: ViewProps & { go?: (area: Area) => void }) {
  const t = useT()
  const view = useView(props, 'headroom')
  const ok = view.ready && view.date
  const query = { network, rule: view.rule, date: view.date }
  const headroom = useV2<Headroom>(ok ? v2Path('/headroom', query) : null)
  const hosting = useV2<Hosting>(ok ? v2Path('/hosting', query) : null)
  const meters = useV2<MeterSites>(ok ? v2Path('/meter-sites', query) : null)
  const rx = useV2<RxMap>(ok ? v2Path('/rx-map', query) : null)
  const trafos = useV2<Transformers>(ok ? v2Path('/transformers', { rule: view.rule, date: view.date }) : null)
  const street = useV2<Street>(ok ? v2Path('/street', { ...query, fix: 'none' }) : null)
  return (
    <div className="v2-page">
      <header className="page-hero">
        <span className="kicker">{t('journey.step', { n: 3 })} · {t('area.planning')}</span>
        <h2>{t('plan.page_title')}</h2>
        <p>{t('plan.page_intro')}</p>
      </header>
      <Controls view={view} />

      <Question n={1} title={t('plan.q1_title')} intro={t('plan.q1_intro')}>
        <Status state={hosting} />
        {hosting.data && <HostingGauge hosting={hosting.data} />}
      </Question>

      <Question n={2} title={t('plan.q2_title')} intro={t('plan.q2_intro')}>
        <Status state={street} />
        {street.data && <MapCard street={street.data} headroom={headroom.data} meters={meters.data} network={network}
          rule={view.rule} date={view.date} />}
        <Status state={headroom} />
      </Question>

      <Question n={3} title={t('plan.q3_title')} intro={t('plan.q3_intro')}>
        <Status state={trafos} />
        {trafos.data && <TransformerList data={trafos.data} />}
      </Question>

      <Question n={4} title={t('plan.q4_title')} intro={t('plan.q4_intro')}>
        <Status state={rx} />
        {rx.data && <RxHeat data={rx.data} />}
      </Question>

      {headroom.data && <Caps headroom={headroom.data} />}
      <Explainer groups={['decision', 'phases', 'range', 'prov']} />
      <NextStep to="try" go={go} />
    </div>
  )
}

function Question({ n, title, intro, children }: { n: number; title: string; intro: string; children: ReactNode }) {
  return (
    <section className="card q-block" aria-labelledby={`q${n}-title`}>
      <div className="q-head"><span className="no">{n}</span><div><h3 id={`q${n}-title`}>{title}</h3><p>{intro}</p></div></div>
      {children}
    </section>
  )
}

function HostingGauge({ hosting }: { hosting: Hosting }) {
  const t = useT()
  const rows = [['plan.hosting_none', hosting.without_fix, ''], ['plan.hosting_vv', hosting.with_volt_var, 'vv']] as const
  return (
    <div className="gauge" data-numbers="hosting capacity">
      {rows.map(([label, run, cls]) => {
        const s = run.adoption_share
        return (
          <div key={label} className="gauge-row" data-hosting>
            <span>{t(label)}</span>
            <div className={`gauge-track ${cls}`} aria-hidden="true">
              <span className="range" style={{ left: pct(s.p10), width: pct(Math.max(s.p90 - s.p10, 0.01)) }} />
              <span className="mid" style={{ left: pct(s.p50) }} />
            </div>
            <span className="v">{t('plan.hosting_value', { p50: pct(s.p50), p10: pct(s.p10), p90: pct(s.p90), kw: Math.round(run.installed_kw.p50) })}</span>
          </div>
        )
      })}
      <div className="gauge-axis" aria-hidden="true"><span>{pct(0)}</span><span>{pct(0.5)}</span><span>{pct(1)}</span></div>
      <p className="muted">{t('plan.hosting_note', { draws: hosting.without_fix.draws })} <Prov kind="modeled" /></p>
    </div>
  )
}

type MapProps = { street: Street; headroom: Headroom | null; meters: MeterSites | null; network: string; rule: string; date: string | null }

function MapCard({ street, headroom, meters, network, rule, date }: MapProps) {
  const t = useT()
  const [layer, setLayer] = useState<Layer>('headroom')
  const [node, setNode] = useState<number | null>(null)
  const homes: HomeView[] = useMemo(() => street.homes.map((h, i) => ({
    node: h.node, phase: street.before.home_phase[i], kwp: h.kwp, cls: `ph-${street.before.home_phase[i].toLowerCase()}`,
    title: t('plan.map_home', { home: i + 1, phase: street.before.home_phase[i] }),
  })), [street, t])
  const markers: Marker[] = []
  if (layer === 'headroom' && headroom) {
    for (const [where, loc] of Object.entries(headroom.locations)) {
      const p = loc.phases
      markers.push({ node: loc.node, kind: 'probe', text: t(`plan.probe_${where}` as StringKey, {
        a: one(p.A?.no_worse_kw ?? 0), b: one(p.B?.no_worse_kw ?? 0), c: one(p.C?.no_worse_kw ?? 0) }) })
    }
  }
  if (layer === 'meters' && meters) meters.sites.slice(0, METERS_SHOWN).forEach((m, i) => markers.push({ node: m.node, text: String(i + 1) }))
  if (layer === 'connect' && node !== null) markers.push({ node, text: '+' })
  return (
    <div className="q-block">
      <div className="segmented" role="tablist" aria-label={t('plan.layers')}>
        {LAYERS.map((l) => (
          <button key={l} role="tab" aria-selected={layer === l} className="seg" aria-pressed={layer === l} onClick={() => setLayer(l)}>
            {t(`plan.layer_${l}` as StringKey)}
          </button>
        ))}
      </div>
      <p className="muted">{t(`plan.layer_${layer}_intro` as StringKey)}</p>
      <div className="street-scroll">
        <StreetMap layout={street.layout} homes={homes} markers={markers} onNode={layer === 'connect' ? setNode : undefined}
          selectedNode={node} trafoLabel={t('player.trafo', { kva: Math.round(street.trafo_kva) })} trafoSub={t('player.trafo_sub')}
          label={t('plan.map_label', { homes: street.homes.length })} />
      </div>
      {layer === 'headroom' && headroom && <HeadroomCells headroom={headroom} />}
      {layer === 'connect' && <ConnectionPanel node={node} network={network} rule={rule} date={date} />}
      {layer === 'meters' && meters && <MeterList data={meters} />}
    </div>
  )
}

function HeadroomCells({ headroom }: { headroom: Headroom }) {
  const t = useT()
  return (
    <div className="split-2" data-numbers="headroom">
      {Object.entries(headroom.locations).map(([where, loc]) => (
        <div key={where} className="where-row">
          <h4>{t(`plan.where_${where}` as StringKey, { node: loc.node })} <Prov kind="modeled" /></h4>
          <div className="phase-cells">
            {Object.entries(loc.phases).map(([ph, h]) => (
              <div key={ph} className="phase-cell" style={{ borderTopColor: `var(--ph-${ph.toLowerCase()})` }}>
                <span className="k">{t('plan.phase_cell', { phase: ph })}</span>
                <span className="v">{one(h.no_worse_kw)}<small className="k"> kW</small></span>
                <span className="k">{h.binding_limit ? bindingText(t, h.binding_limit) : t('plan.no_limit')}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
      <p className="muted">{t('plan.headroom_base', { share: pct(headroom.adoption), steps: headroom.baseline_unsafe_steps })} {t('plan.headroom_note')}</p>
    </div>
  )
}

function MeterList({ data }: { data: MeterSites }) {
  const t = useT()
  return (
    <ol className="rank-list" data-numbers="meter sites" aria-label={t('plan.meter_title')}>
      {data.sites.slice(0, METERS_SHOWN).map((s, i) => (
        <li key={s.node} className="rank-item">
          <span className="pos">{i + 1}</span>
          <span className="name">{t('plan.meter_node', { node: s.node })}<small>{t('plan.meter_why', { dv: s.dv_per_kw_v.toFixed(2), homes: s.homes_downstream })}</small></span>
          <span className="bar"><span style={{ width: pct(s.score / data.sites[0].score) }} /></span>
          <span className="v">{t('plan.meter_dist', { m: Math.round(s.distance_m) })}</span>
        </li>
      ))}
      <li className="muted">{t('plan.meter_note', { probe: data.probe_kw })} <Prov kind="modeled" /></li>
    </ol>
  )
}

function TransformerList({ data }: { data: Transformers }) {
  const t = useT()
  const top = Math.max(...data.transformers.map((r) => r.share_of_headroom_used), 1)
  return (
    <ol className="rank-list" data-numbers="transformer ranking" aria-label={t('plan.trafo_title')}>
      {data.transformers.map((r, i) => (
        <li key={r.id} className="rank-item" data-transformer={r.id}>
          <span className="pos">{i + 1}</span>
          <span className="name">{r.label}<small>{t('plan.trafo_line', { connected: one(r.connected_kw),
            room: r.at_search_limit ? t('plan.trafo_at_least', { kw: one(r.headroom_kw) }) : one(r.headroom_kw) })}</small></span>
          <span className="bar"><span style={{ width: pct(r.share_of_headroom_used / top) }} /></span>
          <span className="v">{t('plan.trafo_times', { x: one(r.share_of_headroom_used) })}</span>
        </li>
      ))}
      <li className="muted">{t('plan.trafo_note')} <Prov kind="benchmark" /></li>
    </ol>
  )
}

function RxHeat({ data }: { data: RxMap }) {
  const t = useT()
  const rs = [...new Set(data.cells.map((c) => c.r_scale))]
  const xs = [...new Set(data.cells.map((c) => c.x_scale))]
  const cell = (r: number, x: number) => data.cells.find((c) => c.r_scale === r && c.x_scale === x)
  const max = Math.max(...data.cells.map((c) => c.volt_var_reduction_v), 0.1)
  const base = cell(1, 1)
  return (
    <div className="rx-grid" data-numbers="rx map" role="table" aria-label={t('plan.q4_title')}>
      {base && <p className="muted">{t('plan.rx_intro', { without: one(base.peak_v_without), vv: one(base.peak_v_volt_var), limit: one(data.vmax_v) })}</p>}
      <div className="rx-row" role="row">
        <span className="rx-head" role="columnheader">{t('plan.rx_corner')}</span>
        {xs.map((x) => <span key={x} className="rx-head" role="columnheader">{t('plan.rx_x', { x: one(x) })}</span>)}
      </div>
      {rs.map((r) => (
        <div key={r} className="rx-row" role="row">
          <span className="rx-head" role="rowheader">{t('plan.rx_r', { r: one(r) })}</span>
          {xs.map((x) => {
            const c = cell(r, x)
            const k = c ? c.volt_var_reduction_v / max : 0
            return <span key={x} role="cell" className="rx-cell" style={{ background: `rgba(31, 99, 214, ${0.08 + k * 0.55})`, color: k > 0.6 ? '#fff' : 'var(--ink)' }}>
              {c ? `−${one(c.volt_var_reduction_v)}` : ''}</span>
          })}
        </div>
      ))}
      <p className="muted">{t('plan.rx_note')} <Prov kind="modeled" /></p>
    </div>
  )
}

function Caps({ headroom }: { headroom: Headroom }) {
  const t = useT()
  return (
    <details className="more" data-numbers="state caps">
      <summary>{t('plan.caps_title')}</summary>
      <p className="muted">{t('plan.caps_installed', { kw: one(headroom.installed_kw) })} <Prov kind="benchmark" /></p>
      <div className="table-scroll">
        <table className="data-table" aria-label={t('plan.caps_title')}>
          <thead><tr>{(['col_state', 'col_cap_pct', 'col_cap_kw', 'col_share', 'col_status'] as const).map((k) => <th key={k} scope="col">{t(`plan.${k}`)}</th>)}</tr></thead>
          <tbody>
            {Object.entries(headroom.flat_caps).map(([state, c]) => (
              <tr key={state}><th scope="row">{state}</th><td>{c.cap_pct}</td><td>{one(c.cap_kw)}</td><td>{pct(c.installed_share_of_cap)}</td><td>{c.tag}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
