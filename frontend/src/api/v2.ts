import { useEffect, useState } from 'react'

/** Typed client for /api/v2. Heavy results come from cache; a cache miss answers with a job to poll. */
export const V2_BASE = '/api/v2'
export const POLL_MS = 2000

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

async function fetchJSON(url: string, body?: string): Promise<unknown> {
  const res = await (body === undefined ? fetch(url)
    : fetch(url, { method: 'POST', body, headers: { 'content-type': 'application/json' } }))
  let reply: unknown = null
  try { reply = await res.json() } catch { reply = null }
  if (!res.ok) throw new Error((reply as ErrorBody | null)?.error?.message ?? `request failed (${res.status})`)
  return reply
}

const JOB_STATES = ['queued', 'running', 'done', 'failed']
const isJob = (body: unknown): body is JobBody =>
  typeof body === 'object' && body !== null && 'job_id' in body && JOB_STATES.includes((body as JobBody).status)

/** Load a v2 resource; `running` while its job computes (polled every 2 s), then `done` with the result.
 *  With a `body` (a JSON string) the request is a POST; the job it starts is still polled with GET. */
export function useV2<T>(path: string | null, body?: string): V2State<T> {
  const key = path === null ? null : `${path} ${body ?? ''}`
  const idle: V2State<T> = { status: path ? 'loading' : 'done', data: null, error: null, jobId: null }
  const [state, setState] = useState<{ key: string | null } & V2State<T>>({ key, ...idle })

  useEffect(() => {
    if (!path) return
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const set = (s: V2State<T>) => { if (alive) setState({ key, ...s }) }
    const fail = (e: unknown) => set({ status: 'error', data: null, error: e instanceof Error ? e.message : String(e), jobId: null })
    const handle = (reply: unknown) => {
      if (!alive) return
      if (!isJob(reply)) return set({ status: 'done', data: reply as T, error: null, jobId: null })
      if (reply.status === 'done') return set({ status: 'done', data: reply.result as T, error: null, jobId: reply.job_id })
      if (reply.status === 'failed') return fail(new Error(reply.error ?? 'the computation failed'))
      set({ status: 'running', data: null, error: null, jobId: reply.job_id })
      timer = setTimeout(() => { fetchJSON(`${V2_BASE}/jobs/${encodeURIComponent(reply.job_id)}`).then(handle, fail) }, POLL_MS)
    }
    fetchJSON(`${V2_BASE}${path}`, body).then(handle, fail)
    return () => { alive = false; clearTimeout(timer) }
  }, [key, path, body])

  // A new request shows `loading` straight away instead of the previous one's result.
  if (state.key !== key) return idle
  const { key: _ignored, ...current } = state
  void _ignored
  return current
}
