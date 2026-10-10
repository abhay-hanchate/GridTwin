import gsap from 'gsap'
import { useEffect, useRef, useState } from 'react'
import { reducedMotion } from './anim'

/** A number that glides to its new value. React renders it once; GSAP writes the text after that. */
export default function Num({ v, fmt }: { v: number; fmt: (x: number) => string }) {
  const el = useRef<HTMLSpanElement>(null)
  const shown = useRef(v)
  const fmtRef = useRef(fmt)
  useEffect(() => { fmtRef.current = fmt })
  const [first] = useState(() => fmt(v))
  useEffect(() => {
    const write = (x: number) => { shown.current = x; if (el.current) el.current.textContent = fmtRef.current(x) }
    if (reducedMotion() || !Number.isFinite(v) || !Number.isFinite(shown.current)) { write(v); return }
    const o = { x: shown.current }
    const tw = gsap.to(o, { x: v, duration: 0.35, ease: 'power2.out', onUpdate: () => write(o.x) })
    return () => { tw.kill() }
  }, [v])
  return <span ref={el}>{first}</span>
}
