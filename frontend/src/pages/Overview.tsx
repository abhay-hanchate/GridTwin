import type { ReactElement } from 'react'
import { useV2, v2Path } from '../api/v2'
import type { Fixes, Results, Risk } from '../api/v2types'
import type { Area } from '../app/areas'
import { DEFAULT_NETWORK } from '../app/defaults'
import { useView, type ViewProps } from '../app/view'
import Controls from '../components/Controls'
import Explainer, { NextStep } from '../components/Explainer'
import Prov from '../components/Prov'
import Status from '../components/Status'
import StreetPlayer from '../components/street/StreetPlayer'
import { dayName } from '../day'
import { one, volts } from '../format'
import { useLang, useT, type StringKey } from '../i18n'
import { causeSplit } from '../risk'

type Props = ViewProps & { go?: (area: Area) => void }

const JOURNEY: Area[] = ['forecast', 'fixes', 'planning', 'try', 'proof']

const ICONS: Record<'sun' | 'act' | 'ok', ReactElement> = {
  sun: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>,
  act: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M13 2 4 14h7l-1 8 9-12h-7z" /></svg>,
  ok: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z" /><path d="m9 12 2 2 4-4" /></svg>,
}

const scrollTop = () => { if (typeof window.scrollTo === 'function') try { window.scrollTo({ top: 0 }) } catch { /* jsdom */ } }

/** The overview: what GridTwin does, the street playing out the day, the answer in plain words, and the way through
 *  the project. Every number comes from /risk, /fixes, /street or /results for the chosen day and rule. */
export default function Overview({ network = DEFAULT_NETWORK, go, ...props }: Props) {
  const t = useT()
  const view = useView(props)
  const query = { network, rule: view.rule, date: view.date }
  const risk = useV2<Risk>(view.ready && view.date ? v2Path('/risk', query) : null)
  const fixes = useV2<Fixes>(view.ready && view.date ? v2Path('/fixes', query) : null)
  const results = useV2<Results>('/results')
  const open = (area: Area) => () => { go?.(area); scrollTop() }

  return (
    <div className="v2-page overview">
      <section className="hero">
        <div className="reveal">
          <span className="eyebrow">{t('overview.eyebrow')}</span>
          <h2>{t('overview.title_a')} <em>{t('overview.title_em')}</em> {t('overview.title_b')}</h2>
          <p className="lede">{t('overview.lede')}</p>
          <div className="cta-row">
            <a className="btn btn-primary" href="#watch">{t('overview.cta_watch')} <span className="arrow" aria-hidden="true">▶</span></a>
            <button className="btn btn-ghost" onClick={open('forecast')}>{t('overview.cta_forecast')} <span className="arrow" aria-hidden="true">→</span></button>
          </div>
        </div>
        <div className="hero-facts reveal reveal-2">
          {(['sun', 'act', 'ok'] as const).map((k) => (
            <div key={k} className="fact">
              <span className={`icon ${k}`}>{ICONS[k]}</span>
              <div><h3>{t(`overview.fact_${k}_title` as StringKey)}</h3><p>{t(`overview.fact_${k}` as StringKey)}</p></div>
            </div>
          ))}
        </div>
      </section>

      <section className="section" id="watch" aria-labelledby="watch-title">
        <header>
          <span className="eyebrow">{t('overview.watch_eyebrow')}</span>
          <h2 id="watch-title">{t('overview.watch_title')}</h2>
          <p>{t('overview.watch_intro')}</p>
        </header>
        <Controls view={view} />
        <div className="card">{view.ready && <StreetPlayer network={network} rule={view.rule} date={view.date} />}</div>
      </section>

      <Status state={risk} />
      {risk.data && <Summary risk={risk.data} fixes={fixes.data} rule={(view.band?.label ?? view.rule).split(':')[0]} vmax={view.band?.vmax_v} />}

      <section className="section" aria-labelledby="journey-title">
        <header>
          <span className="eyebrow">{t('overview.journey_eyebrow')}</span>
          <h2 id="journey-title">{t('overview.journey_title')}</h2>
          <p>{t('overview.journey_intro')}</p>
        </header>
        <ol className="journey">
          {JOURNEY.map((a, i) => (
            <li key={a}>
              <button className="journey-card" onClick={open(a)} data-area={a}>
                <span className="no">{i + 1}</span>
                <span className="eyebrow">{t(`area.${a}` as StringKey)}</span>
                <span className="q">{t(`overview.q_${a}` as StringKey)}</span>
                <p>{t(`overview.a_${a}` as StringKey)}</p>
                <span className="go">{t('overview.open')} →</span>
              </button>
            </li>
          ))}
        </ol>
      </section>

      {results.data && <Trust results={results.data} onOpen={open('proof')} />}

      <Explainer groups={['levels', 'cause', 'phases', 'voltage', 'prov']} />
      <NextStep to="forecast" go={go} />
    </div>
  )
}

function Summary({ risk, fixes, rule, vmax }: { risk: Risk; fixes: Fixes | null; rule: string; vmax?: number }) {
  const t = useT()
  const { lang } = useLang()
  const share = causeSplit(risk).solarShare
  const v = fixes?.verdict
  const byId = new Map((fixes?.outcomes ?? []).map((o) => [o.id, o.label]))
  const best = v ? byId.get((v.safe_action_found ? v.recommended : v.closest) ?? '') : undefined
  const day = dayName(risk.date, lang, t)
  return (
    <section className="card summary reveal reveal-3" aria-labelledby="summary-title" data-numbers="overview summary">
      <span className="eyebrow" id="summary-title">{t('overview.summary_eyebrow', { day })}</span> <Prov kind="modeled" />
      <p className="summary-line">
        {risk.level === 'ok'
          ? t('overview.plain_ok', { rule })
          : <>{t('overview.plain_hours', { rule, hours: one(risk.expected_unsafe_hours.mean) })}{' '}
            {share !== null && (share >= 0.5
              ? <span className="sun">{t('overview.plain_solar')}</span>
              : <span className="grid">{t('overview.plain_grid')}</span>)}{' '}
            {v && best && (v.safe_action_found
              ? t('overview.plain_fix', { fix: best })
              : <span className="act">{t('overview.plain_nofix', { fix: best })}</span>)}</>}
      </p>
      <div className="stats">
        <div className={`stat ${risk.level === 'ok' ? 'ok' : 'act'}`}>
          <span className="label">{t('overview.f_hours')}</span>
          <span className="value">{one(risk.expected_unsafe_hours.mean)}<small>{t('overview.unit_h')}</small></span>
          {risk.expected_unsafe_hours.p10 !== null && risk.expected_unsafe_hours.p90 !== null && (
            <p>{t('home.hours_range', { p10: one(risk.expected_unsafe_hours.p10), p90: one(risk.expected_unsafe_hours.p90) })}</p>
          )}
        </div>
        <div className="stat">
          <span className="label">{t('overview.f_peak')}</span>
          <span className="value">{volts(risk.peak_voltage_v.p50)}<small>V</small></span>
          <p>{vmax !== undefined ? t('overview.f_peak_note', { vmax: one(vmax) }) : ''}</p>
        </div>
        <div className="stat">
          <span className="label">{t('overview.f_cause')}</span>
          <span className="value">{share === null ? '—' : `${Math.round(share * 100)}%`}</span>
          <p>{t('overview.f_cause_note')}</p>
        </div>
        <div className="stat">
          <span className="label">{t('overview.f_fix')}</span>
          <span className="value text">{!v ? t('overview.f_fix_pending') : v.safe_action_found ? best ?? '—' : t('overview.f_nofix')}</span>
          <p>{v ? (v.safe_action_found ? t('overview.f_fix_note') : t('overview.f_nofix_note')) : ''}</p>
        </div>
      </div>
    </section>
  )
}

function Trust({ results, onOpen }: { results: Results; onOpen: () => void }) {
  const t = useT()
  const passed = results.gates.filter((g) => g.status === 'pass').length
  return (
    <section className="trust" aria-labelledby="trust-title">
      <span className="score">{passed}<small>/{results.gates.length}</small></span>
      <div>
        <h3 id="trust-title" className="trust-title">{t('overview.trust_title')}</h3>
        <p>{t('overview.trust_text')}</p>
      </div>
      <button className="btn" onClick={onOpen}>{t('overview.trust_cta')} <span className="arrow" aria-hidden="true">→</span></button>
    </section>
  )
}
