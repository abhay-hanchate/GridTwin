import type { V2State } from '../api/v2'
import { useT } from '../i18n'

/** What to show while a v2 resource is not ready: loading, the running job, or the error. Null when done. */
export default function Status({ state }: { state: V2State<unknown> }) {
  const t = useT()
  if (state.status === 'loading') return <div className="loading" role="status">{t('shell.loading')}</div>
  if (state.status === 'running') return <div className="loading running" role="status">{t('shell.running')}</div>
  if (state.status === 'error') return <div className="error" role="alert">{t('shell.error', { message: state.error ?? '' })}</div>
  return null
}
