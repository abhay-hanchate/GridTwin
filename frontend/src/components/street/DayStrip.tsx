import { useEffect } from 'react'
import { useT } from '../../i18n'
import { useCanvas } from './anim'

type Props = {
  t: string[]
  /** kW through the transformer per quarter hour: + drawn from the grid, - sent back */
  grid: number[]
  solar: number[]
  unsafe: boolean[]
  /** the y-scale for the day, shared by both runs when a fix is compared */
  maxKw: number
  step: number
  onStep: (k: number) => void
}

/** The whole day at a glance: power drawn from the grid above the line, power sent back below it, the sun behind,
 *  and the quarter hours that break the rule along the bottom. Drag or use the arrow keys to move through the day. */
export default function DayStrip({ t: times, grid, solar, unsafe, maxKw, step, onStep }: Props) {
  const t = useT()
  const { ref, w, h, ctx } = useCanvas()
  const n = times.length

  useEffect(() => {
    const c = ctx()
    if (!c) return
    const bandH = 6
    const top = 6
    const bottom = h - bandH - 6
    const mid = top + (bottom - top) / 2
    const half = (bottom - top) / 2
    const bw = w / n
    const X = (k: number) => k * bw
    c.clearRect(0, 0, w, h)
    // sunlight, faint, behind everything
    c.fillStyle = 'rgba(245,158,11,0.10)'
    c.beginPath(); c.moveTo(0, mid)
    solar.forEach((s, k) => c.lineTo(X(k) + bw / 2, mid - (s / maxKw) * half))
    c.lineTo(w, mid); c.closePath(); c.fill()
    // grid flow: one bar per quarter hour
    grid.forEach((g, k) => {
      const hh = (Math.abs(g) / maxKw) * half
      c.fillStyle = g < 0 ? (k <= step ? '#f59e0b' : 'rgba(245,158,11,0.45)') : (k <= step ? '#0ea5e9' : 'rgba(14,165,233,0.4)')
      c.fillRect(X(k) + 0.5, g < 0 ? mid : mid - hh, Math.max(1, bw - 1), Math.max(0.5, hh))
    })
    c.strokeStyle = 'rgba(19,32,51,0.25)'; c.lineWidth = 1
    c.beginPath(); c.moveTo(0, mid); c.lineTo(w, mid); c.stroke()
    // the quarter hours that break the rule
    unsafe.forEach((u, k) => {
      if (!u) return
      c.fillStyle = '#e3433f'
      c.fillRect(X(k), h - bandH, Math.ceil(bw), bandH)
    })
    // the playhead
    const px = X(step) + bw / 2
    c.strokeStyle = '#132033'; c.lineWidth = 2
    c.beginPath(); c.moveTo(px, 0); c.lineTo(px, h); c.stroke()
    c.fillStyle = '#132033'
    c.beginPath(); c.arc(px, mid - (grid[step] / maxKw) * half, 4.5, 0, Math.PI * 2); c.fill()
  }, [ctx, w, h, n, grid, solar, unsafe, maxKw, step])

  return (
    <div className="daystrip">
      <div className="ds-plot">
        <canvas ref={ref} className="ds-canvas" aria-hidden="true" />
        <span className="ds-tag up" aria-hidden="true">{t('flow.draw')} ↑</span>
        <span className="ds-tag down" aria-hidden="true">{t('flow.back')} ↓</span>
        <input type="range" min={0} max={n - 1} value={step} aria-label={t('player.time')} aria-valuetext={times[step]}
          onChange={(e) => onStep(Number(e.target.value))} />
      </div>
      <div className="axis" aria-hidden="true">{[0, 24, 48, 72, n - 1].map((i) => <span key={i}>{times[i]}</span>)}</div>
    </div>
  )
}
