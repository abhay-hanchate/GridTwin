import { useV2, V2_BASE, v2Path } from '../api/v2'
import type { Risk, Rule } from '../api/v2types'
import { DEFAULT_NETWORK } from '../app/defaults'
import { useView, type ViewProps } from '../app/view'
import Controls from '../components/Controls'
import Prov from '../components/Prov'
import RiskStrip from '../components/RiskStrip'
import Status from '../components/Status'
import Verdict from '../components/Verdict'
import { one, stepTime, volts } from '../format'
import { useLang, useT } from '../i18n'

// Watch and act levels of feature D1; the API states the ones it used and these are only the fallback.
const DEFAULT_THRESHOLDS = { watch: 0.2, act: 0.5 }

/** Tomorrow's risk. The rule and day can be owned by the caller (shared with Fixes) or by the page itself. */
export default function Home({ network = DEFAULT_NETWORK, ...props }: ViewProps) {
  const t = useT()
  const { lang } = useLang()
  const view = useView(props, 'risk')
  const risk = useV2<Risk>(view.ready ? v2Path('/risk', { network, rule: view.rule, date: view.date }) : null)
  // The printable evening report (F2) for exactly what this page shows: same day, street, rule and language.
  const report = risk.data && `${V2_BASE}${v2Path('/report', { date: risk.data.date, network, rule: view.rule, lang })}`

  return (
    <div className="v2-page">
      <Controls view={view} answered={risk.data?.date} />
      <Status state={risk} />
      {risk.data && <RiskView risk={risk.data} band={view.band} />}
      {report && <p><a className="report-link" href={report} target="_blank" rel="noopener">{t('home.report')}</a></p>}
      {risk.data && (
        <p className="note" role="note">{t(risk.data.calibration?.reliable ? 'home.calibrated' : 'home.uncalibrated')}</p>
      )}
    </div>
  )
}

function RiskView({ risk, band }: { risk: Risk; band?: Rule }) {
  const t = useT()
  const { watch, act } = risk.thresholds ?? DEFAULT_THRESHOLDS
  const times = risk.t ?? risk.p_unsafe.map((_, i) => stepTime(i))
  const hours = risk.expected_unsafe_hours
  const peak = risk.peak_voltage_v
  return (
    <>
      <Verdict risk={risk} times={times} act={act} />
      <section className="card" data-numbers="probability strip">
        <h3>{t('home.strip_title')} <Prov kind="modeled" /></h3>
        <RiskStrip p={risk.p_unsafe} times={times} watch={watch} act={act} />
      </section>
      <div className="kpis-v2">
        <section className="card kpi" data-numbers="expected unsafe hours">
          <div className="label">{t('home.hours')} <Prov kind="modeled" /></div>
          <div className="kpi-value">{t('home.hours_value', { value: one(hours.mean) })}</div>
          <p className="muted">{t('home.hours_range', { p10: one(hours.p10), p90: one(hours.p90) })}</p>
        </section>
        <section className="card kpi" data-numbers="peak voltage">
          <div className="label">{t('home.peak')} <Prov kind="modeled" /></div>
          <div className="kpi-value">{volts(peak.p50)} V</div>
          {band && (
            <p className="muted">{t('home.peak_range', {
              p10: volts(peak.p10), p90: volts(peak.p90), vmin: one(band.vmin_v), vmax: one(band.vmax_v),
            })}</p>
          )}
        </section>
      </div>
      <p className="muted inputs">{t('home.inputs', {
        solar: risk.provenance.solar ?? '', demand: risk.provenance.demand ?? '', voltage: risk.provenance.voltage ?? '',
      })}</p>
      {risk.provenance.anchor && <p className="muted inputs">{t('home.anchor', { note: risk.provenance.anchor })}</p>}
    </>
  )
}
