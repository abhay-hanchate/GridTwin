import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'

/** No animation where the reader asked for less motion, or where there is no browser to animate in (tests). */
export const reducedMotion = () =>
  typeof window === 'undefined' || typeof window.matchMedia !== 'function' || window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** A canvas that follows its box: CSS size, device-pixel backing store, and whether it is on screen (drawing stops
 *  when it is not). `ctx()` returns a context already scaled to CSS pixels, or null where canvas is unavailable. */
export function useCanvas(): { ref: RefObject<HTMLCanvasElement | null>; w: number; h: number; visible: RefObject<boolean>; ctx: () => CanvasRenderingContext2D | null } {
  const ref = useRef<HTMLCanvasElement | null>(null)
  const visible = useRef(true)
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([e]) => setSize({ w: Math.round(e.contentRect.width), h: Math.round(e.contentRect.height) }))
    ro.observe(el)
    let io: IntersectionObserver | undefined
    if (typeof IntersectionObserver !== 'undefined') {
      io = new IntersectionObserver(([e]) => { visible.current = e.isIntersecting })
      io.observe(el)
    }
    return () => { ro.disconnect(); io?.disconnect() }
  }, [])
  const ctx = useCallback(() => {
    const el = ref.current
    if (!el || !size.w || !size.h) return null
    const c = el.getContext?.('2d') ?? null
    if (!c) return null
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    if (el.width !== Math.round(size.w * dpr) || el.height !== Math.round(size.h * dpr)) {
      el.width = Math.round(size.w * dpr)
      el.height = Math.round(size.h * dpr)
    }
    c.setTransform(dpr, 0, 0, dpr, 0, 0)
    return c
  }, [size.w, size.h])
  return { ref, w: size.w, h: size.h, visible, ctx }
}

/** True on narrow screens (phones), and again whenever the window crosses the width. */
export function useNarrow(maxPx = 640): boolean {
  const query = `(max-width: ${maxPx}px)`
  const get = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(query).matches
  const [narrow, setNarrow] = useState(get)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia(query)
    const on = () => setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return narrow
}
