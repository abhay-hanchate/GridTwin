import { useT, type StringKey } from '../i18n'
import type { Provenance } from '../api/v2types'

/** The provenance tag every number block carries: observed, modeled or benchmark. */
export default function Prov({ kind }: { kind: Provenance }) {
  const t = useT()
  return <span className={`prov prov-${kind}`} data-provenance={kind}>{t(`prov.${kind}` as StringKey)}</span>
}
