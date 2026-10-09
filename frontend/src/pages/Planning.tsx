import { useV2, v2Path } from '../api/v2'
import type { Headroom, Hosting } from '../api/v2types'
import { DEFAULT_NETWORK } from '../app/defaults'
import { useView, type ViewProps } from '../app/view'
import ConnectionForm from '../components/ConnectionForm'
import Controls from '../components/Controls'
import HeadroomTable from '../components/HeadroomTable'
import HostingCard from '../components/HostingCard'
import Status from '../components/Status'
import { useT } from '../i18n'

/** Planning (E1-E3, P9.5): per-phase headroom beside the flat caps, hosting capacity, and the connection check. */
export default function Planning({ network = DEFAULT_NETWORK, ...props }: ViewProps) {
  const t = useT()
  const view = useView(props, 'headroom')
  const query = { network, rule: view.rule, date: view.date }
  const headroom = useV2<Headroom>(view.ready ? v2Path('/headroom', query) : null)
  const hosting = useV2<Hosting>(view.ready ? v2Path('/hosting', query) : null)
  return (
    <div className="v2-page">
      <Controls view={view} answered={headroom.data?.date} />
      <p className="muted">{t('plan.intro')}</p>
      <Status state={headroom} />
      {headroom.data && <HeadroomTable headroom={headroom.data} />}
      <Status state={hosting} />
      {hosting.data && <HostingCard hosting={hosting.data} />}
      {headroom.data && (
        <ConnectionForm key={`${headroom.data.date}-${view.rule}`} headroom={headroom.data} network={network}
          rule={view.rule} date={view.date} />
      )}
    </div>
  )
}
