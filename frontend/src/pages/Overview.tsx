import { ShieldCheck, Sun, Zap } from 'lucide-react'
import { useV2, v2Path } from '../api/v2'
import type { Fixes, Risk } from '../api/v2types'
import type { Area } from '../app/areas'
import { DEFAULT_NETWORK } from '../app/defaults'
import { useView, type ViewProps } from '../app/view'
import Explainer, { NextStep } from '../components/Explainer'
import CountUp from '../components/CountUp'
import HeroStreet from '../components/HeroStreet'
import Info from '../components/Info'
import Prov from '../components/Prov'
import Status from '../components/Status'
import { dayName } from '../day'
import { one, volts } from '../format'
import { useLang, useT, type StringKey } from '../i18n'
import { causeSplit } from '../risk'

type Props = ViewProps & { go?: (area: Area) => void }

const JOURNEY: Area[] = ['forecast', 'fixes', 'planning', 'try', 'control', 'surrogate']

const scrollTop = () => { if (typeof window.scrollTo === 'function') try { window.scrollTo({ top: 0 }) } catch { /* jsdom */ } }

/** The overview: what GridTwin does, the answer in plain words, and the way through the project.
 *  Every number comes from /risk, /fixes or /results for the chosen day and rule. */
export default function Overview({ network = DEFAULT_NETWORK, go, ...props }: Props) {
  const t = useT()
  const view = useView(props)
  const query = { network, rule: view.rule, date: view.date }
  const risk = useV2<Risk>(view.ready && view.date ? v2Path('/risk', query) : null)
  const fixes = useV2<Fixes>(view.ready && view.date ? v2Path('/fixes', query) : null)
  const open = (area: Area) => () => { go?.(area); scrollTop() }

  return (
    <div className="v2-page overview">
      <section className="hero">
        <div className="reveal">
          <span className="eyebrow">{t('overview.eyebrow')}</span>
          <h2>{t('overview.title_a')} <em>{t('overview.title_em')}</em> {t('overview.title_b')}</h2>
          <p className="lede">{t('overview.lede')}</p>
          <div className="cta-row">
            <button className="btn btn-ghost" onClick={open('forecast')}>{t('overview.cta_forecast')} <span className="arrow" aria-hidden="true">→</span></button>
          </div>
        </div>
        <div className="hero-art reveal reveal-2">
          <HeroStreet />
          <ul className="hero-chips">
            {(['sun', 'act', 'ok'] as const).map((k) => {
              const Icon = { sun: Sun, act: Zap, ok: ShieldCheck }[k]
              return (
                <li key={k} className={`chip-fact ${k}`}>
                  <Icon size={16} strokeWidth={2.2} aria-hidden="true" />
                  <span>{t(`overview.fact_${k}_title` as StringKey)}</span>
                  <Info>{t(`overview.fact_${k}` as StringKey)}</Info>
                </li>
              )
            })}
          </ul>
        </div>
      </section>

      <Status state={risk} />
      {risk.data && <Summary risk={risk.data} fixes={fixes.data} rule={(view.band?.label ?? view.rule).split(':')[0]} vmax={view.band?.vmax_v} />}

      <section className="section" aria-labelledby="journey-title">
        <header>
          <span className="eyebrow">{t('overview.journey_eyebrow')}</span>
          <h2 id="journey-title">{t('overview.journey_title')}</h2>
        </header>
        <ol className="journey">
          {JOURNEY.map((a, i) => (
            <li key={a}>
              <button className="journey-card" onClick={open(a)} data-area={a}>
                <span className="no">{i + 1}</span>
                <span className="eyebrow">{t(`area.${a}` as StringKey)}</span>
                <span className="q">{t(`overview.q_${a}` as StringKey)}</span>
                <span className="go">{t('overview.open')} <span className="arrow" aria-hidden="true">→</span></span>
              </button>
            </li>
          ))}
        </ol>
      </section>

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
          <span className="value"><CountUp value={risk.expected_unsafe_hours.mean} format={one} /><small>{t('overview.unit_h')}</small></span>
          {risk.expected_unsafe_hours.p10 !== null && risk.expected_unsafe_hours.p90 !== null && (
            <p>{t('home.hours_range', { p10: one(risk.expected_unsafe_hours.p10), p90: one(risk.expected_unsafe_hours.p90) })}</p>
          )}
        </div>
        <div className="stat">
          <span className="label">{t('overview.f_peak')}</span>
          <span className="value"><CountUp value={risk.peak_voltage_v.p50} format={volts} /><small>V</small></span>
          <p>{vmax !== undefined ? t('overview.f_peak_note', { vmax: one(vmax) }) : ''}</p>
        </div>
        <div className="stat">
          <span className="label">{t('overview.f_cause')}</span>
          <span className="value">{share === null ? '—' : <CountUp value={share * 100} format={(n) => `${Math.round(n)}%`} />}</span>
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
