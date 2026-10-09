import { useEffect, useState } from 'react'

/** Typed client for /api/v2. Heavy results come from cache; a cache miss answers with a job to poll. */
export const V2_BASE = '/api/v2'
export const POLL_MS = 2000
/** Build-time switch: VITE_DASHBOARD=v2 shows the v2 layout. */
export const V2_DASHBOARD = import.meta.env.VITE_DASHBOARD === 'v2'

export type V2Status = 'loading' | 'running' | 'done' | 'error'
export interface V2State<T> { status: V2Status; data: T | null; error: string | null; jobId: string | null }

type JobBody = { status: 'queued' | 'running' | 'done' | 'failed'; job_id: string; result?: unknown; error?: string }
type ErrorBody = { error?: { code?: string; message?: string } }

export function v2Path(route: string, params: Record<string, string | number | null | undefined> = {}): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  }
  const qs = query.toString()
  return qs ? `${route}?${qs}` : route
}

async function fetchJSON(url: string): Promise<unknown> {
  const res = await fetch(url)
  let body: unknown = null
  try { body = await res.json() } catch { body = null }
  if (!res.ok) throw new Error((body as ErrorBody | null)?.error?.message ?? `request failed (${res.status})`)
  return body
}

const load = fetchJSON

const JOB_STATES = ['queued', 'running', 'done', 'failed']
const isJob = (body: unknown): body is JobBody =>
  typeof body === 'object' && body !== null && 'job_id' in body && JOB_STATES.includes((body as JobBody).status)

/** Load a v2 resource; `running` while its job computes (polled every 2 s), then `done` with the result. */
export function useV2<T>(path: string | null): V2State<T> {
  const idle: V2State<T> = { status: path ? 'loading' : 'done', data: null, error: null, jobId: null }
  const [state, setState] = useState<{ path: string | null } & V2State<T>>({ path, ...idle })

  useEffect(() => {
    if (!path) return
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const set = (s: V2State<T>) => { if (alive) setState({ path, ...s }) }
    const fail = (e: unknown) => set({ status: 'error', data: null, error: e instanceof Error ? e.message : String(e), jobId: null })
    const handle = (body: unknown) => {
      if (!alive) return
      if (!isJob(body)) return set({ status: 'done', data: body as T, error: null, jobId: null })
      if (body.status === 'done') return set({ status: 'done', data: body.result as T, error: null, jobId: body.job_id })
      if (body.status === 'failed') return fail(new Error(body.error ?? 'the computation failed'))
      set({ status: 'running', data: null, error: null, jobId: body.job_id })
      timer = setTimeout(() => { load(`${V2_BASE}/jobs/${encodeURIComponent(body.job_id)}`).then(handle, fail) }, POLL_MS)
    }
    load(`${V2_BASE}${path}`).then(handle, fail)
    return () => { alive = false; clearTimeout(timer) }
  }, [path])

  // A new path shows `loading` straight away instead of the previous path's result.
  if (state.path !== path) return idle
  const { path: _ignored, ...current } = state
  void _ignored
  return current
}
