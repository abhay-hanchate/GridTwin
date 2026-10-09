import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { v2Path, useV2 } from './v2'

function Probe({ path }: { path: string | null }) {
  const s = useV2<{ answer: number }>(path)
  return <p>{s.status}{s.data ? ` ${s.data.answer}` : ''}{s.error ? ` ${s.error}` : ''}</p>
}

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

beforeEach(() => vi.useFakeTimers())
afterEach(() => { cleanup(); vi.useRealTimers() })

const flush = () => act(async () => { await vi.advanceTimersByTimeAsync(0) })

describe('useV2', () => {
  it('a running response shows the progress state, polls the job every 2 s, then shows the result', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => json({ status: 'running', job_id: 'j1' }))
      .mockImplementationOnce(() => json({ status: 'running', job_id: 'j1' }))
      .mockImplementationOnce(() => json({ status: 'done', job_id: 'j1', result: { answer: 42 } }))
    render(<Probe path="/risk?date=2025-05-15" />)
    await flush()
    expect(screen.getByText('running')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByText('running')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByText('done 42')).toBeTruthy()
    expect(fetchMock.mock.calls.map((c) => String(c[0]))).toEqual(
      ['/api/v2/risk?date=2025-05-15', '/api/v2/jobs/j1', '/api/v2/jobs/j1'])
  })

  it('a finished response is shown directly', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(() => json({ answer: 7 }))
    render(<Probe path="/rules" />)
    await flush()
    expect(screen.getByText('done 7')).toBeTruthy()
  })

  it('the API error model becomes a readable error, never a stack trace', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () => json({ error: { code: 'not_found', message: 'unknown network x', details: {} } }, 404))
    render(<Probe path="/risk?network=x" />)
    await flush()
    expect(screen.getByText('error unknown network x')).toBeTruthy()
  })

  it('a failed job is an error', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => json({ status: 'queued', job_id: 'j2' }))
      .mockImplementationOnce(() => json({ status: 'failed', job_id: 'j2', error: 'solver crashed' }))
    render(<Probe path="/fixes" />)
    await flush()
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByText('error solver crashed')).toBeTruthy()
  })

  it('stops polling after unmount', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => json({ status: 'running', job_id: 'j3' }))
    const { unmount } = render(<Probe path="/risk" />)
    await flush()
    unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('v2Path', () => {
  it('builds a query string and skips empty values', () => {
    expect(v2Path('/risk', { date: '2025-05-15', rule: 'up_2005', fix: undefined })).toBe('/risk?date=2025-05-15&rule=up_2005')
    expect(v2Path('/rules')).toBe('/rules')
  })
})
