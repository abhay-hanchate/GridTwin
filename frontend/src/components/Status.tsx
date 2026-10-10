import { useEffect, useState } from 'react'
import type { V2State } from '../api/v2'
import { useT } from '../i18n'

/** Grey outlines of a chart and its cards while a result loads, so the page keeps its shape. */
function Skeleton() {
  return (
    <div className="skel" aria-hidden="true">
      <span className="skel-line w40" />
      <span className="skel-block" />
      <span className="skel-row"><span className="skel-card" /><span className="skel-card" /><span className="skel-card" /></span>
    </div>
  )
}

/** Seconds since a job started, so a first-time computation of several minutes visibly moves. */
function useElapsed(active: boolean): number {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!active) return
    const started = Date.now()
    const id = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => { clearInterval(id); setSeconds(0) }
  }, [active])
  return seconds
}

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

/** What to show while a v2 resource is not ready: loading, the running job, or the error. Null when done. */
export default function Status({ state }: { state: V2State<unknown> }) {
  const t = useT()
  const elapsed = useElapsed(state.status === 'running')
  if (state.status === 'loading') {
    return <div className="loading skel-wrap" role="status"><span className="skel-msg">{t('shell.loading')}</span><Skeleton /></div>
  }
  if (state.status === 'running') {
    return (
      <div className="loading running skel-wrap" role="status">
        <span className="skel-msg">{t('shell.running')}</span>
        {elapsed > 0 && <span className="skel-elapsed mono" aria-hidden="true">{clock(elapsed)}</span>}
        <Skeleton />
      </div>
    )
  }
  if (state.status === 'error') return <div className="error" role="alert">{t('shell.error', { message: state.error ?? '' })}</div>
  return null
}
