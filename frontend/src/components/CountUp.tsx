import { useEffect, useRef, useState } from 'react'

const DURATION_MS = 900

function animated(): boolean {
  if (import.meta.env.MODE === 'test' || typeof window.requestAnimationFrame !== 'function') return false
  return !(typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches)
}

/** A figure that counts up when it first appears and glides to its new value when the day or rule changes.
 *  The final text is exactly `format(value)`; only the frames on the way there differ. */
export default function CountUp({ value, format }: { value: number; format: (n: number) => string }) {
  const motion = animated()
  const [shown, setShown] = useState(0)
  const from = useRef(0)
  useEffect(() => {
    if (!motion || !Number.isFinite(value)) return
    const start = performance.now()
    const begin = from.current
    let frame = 0
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / DURATION_MS)
      const eased = 1 - Math.pow(1 - k, 3)
      const v = begin + (value - begin) * eased
      from.current = v
      setShown(k < 1 ? v : value)
      if (k < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value, motion])
  // without motion (tests, reduced motion) the figure is simply the value
  return <span className="count-up">{format(motion && Number.isFinite(value) ? shown : value)}</span>
}
