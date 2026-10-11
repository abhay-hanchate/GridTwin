import gsap from 'gsap'
import { useEffect, useRef } from 'react'
import { useT } from '../i18n'

// The story of GridTwin in one loop: the sun climbs, rooftop panels push power back up the wire, the street's voltage
// rises past the limit (coral), a fix is applied and the voltage settles back inside the limit (green).
const HOUSES = [150, 238, 326, 414]
const BEFORE = 'M24 118 C70 116 96 112 120 100 S168 52 196 40 S236 54 260 84 S300 112 336 116'
const AFTER = 'M24 118 C70 117 96 114 120 108 S168 88 196 84 S236 90 260 100 S300 114 336 116'

export default function HeroStreet() {
  const t = useT()
  const root = useRef<SVGSVGElement>(null)

  useEffect(() => {
    const el = root.current
    if (!el) return
    const reduced = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const q = gsap.utils.selector(el)
    const ctx = gsap.context(() => {
      if (reduced) {
        gsap.set(q('.hs-after'), { opacity: 1, strokeDashoffset: 0 })
        gsap.set(q('.hs-before'), { opacity: 0 })
        gsap.set(q('.hs-ok'), { opacity: 1, scale: 1 })
        return
      }
      const before = el.querySelector<SVGPathElement>('.hs-before')!
      const after = el.querySelector<SVGPathElement>('.hs-after')!
      const lb = before.getTotalLength?.() ?? 400
      const la = after.getTotalLength?.() ?? 400
      gsap.set(before, { strokeDasharray: lb, strokeDashoffset: lb, opacity: 1 })
      gsap.set(after, { strokeDasharray: la, strokeDashoffset: la, opacity: 1 })
      gsap.set(q('.hs-ok'), { opacity: 0, scale: 0.6, transformOrigin: '50% 50%' })
      gsap.set(q('.hs-alert'), { opacity: 0 })
      gsap.set(q('.hs-sun'), { x: -150, y: 70 })
      gsap.set(q('.hs-flow'), { opacity: 0 })
      gsap.set(q('.hs-panel'), { fill: '#3f5a45' })

      gsap.to(q('.hs-rays'), { rotate: 360, transformOrigin: '50% 50%', duration: 24, ease: 'none', repeat: -1 })
      gsap.to(q('.hs-flow'), { strokeDashoffset: -60, duration: 1.4, ease: 'none', repeat: -1 })

      const tl = gsap.timeline({ repeat: -1, repeatDelay: 0.6, defaults: { ease: 'power3.inOut' } })
      tl.to(q('.hs-sun'), { x: 0, y: 0, duration: 2.4 })
        .to(q('.hs-panel'), { fill: '#e3a83f', duration: 0.8, stagger: 0.12 }, '-=1.2')
        .to(q('.hs-flow'), { opacity: 1, duration: 0.5 }, '<')
        .to(before, { strokeDashoffset: 0, duration: 2.2, ease: 'power2.inOut' }, '<')
        .to(q('.hs-alert'), { opacity: 1, duration: 0.3, yoyo: true, repeat: 3 }, '-=1.1')
        .to(before, { opacity: 0.18, duration: 0.6 }, '+=0.3')
        .to(after, { strokeDashoffset: 0, duration: 1.6, ease: 'power2.out' }, '<')
        .to(q('.hs-alert'), { opacity: 0, duration: 0.3 }, '<')
        .to(q('.hs-ok'), { opacity: 1, scale: 1, duration: 0.6, ease: 'back.out(2)' }, '-=0.5')
        .to({}, { duration: 1.8 })
        .to(q('.hs-sun'), { x: 150, y: 70, duration: 1.8 })
        .to(q('.hs-panel'), { fill: '#3f5a45', duration: 0.6 }, '<')
        .to(q('.hs-flow'), { opacity: 0, duration: 0.4 }, '<')
        .to([before, after], { opacity: 0, duration: 0.5 }, '<')
        .to(q('.hs-ok'), { opacity: 0, duration: 0.4 }, '<')
        .set(before, { strokeDashoffset: lb, opacity: 1 })
        .set(after, { strokeDashoffset: la, opacity: 1 })
        .set(q('.hs-sun'), { x: -150, y: 70 })
    }, el)
    return () => ctx.revert()
  }, [])

  return (
    <figure className="hero-street">
      <svg ref={root} viewBox="0 0 560 380" role="img" aria-label={t('hero.alt')}>
        <defs>
          <linearGradient id="hs-sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#d2edd7" stopOpacity="0.9" />
            <stop offset="1" stopColor="#f2f2f2" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="hs-trace" x1="0" x2="1">
            <stop offset="0" stopColor="#5d7a5e" />
            <stop offset="0.45" stopColor="#d96868" />
            <stop offset="0.75" stopColor="#d96868" />
            <stop offset="1" stopColor="#88a886" />
          </linearGradient>
          <linearGradient id="hs-good" x1="0" x2="1">
            <stop offset="0" stopColor="#4f6d51" />
            <stop offset="1" stopColor="#88a886" />
          </linearGradient>
          <radialGradient id="hs-sunfill">
            <stop offset="0" stopColor="#f3d27a" />
            <stop offset="1" stopColor="#e3a83f" />
          </radialGradient>
        </defs>

        <rect className="hs-sky" x="0" y="0" width="560" height="380" rx="26" fill="url(#hs-sky)" />

        {/* sun */}
        <g className="hs-sun">
          <g className="hs-rays" stroke="#e3a83f" strokeWidth="3" strokeLinecap="round" opacity="0.55">
            {Array.from({ length: 10 }, (_, i) => {
              const a = (i / 10) * Math.PI * 2
              return <line key={i} x1={440 + Math.cos(a) * 34} y1={86 + Math.sin(a) * 34} x2={440 + Math.cos(a) * 44} y2={86 + Math.sin(a) * 44} />
            })}
          </g>
          <circle cx="440" cy="86" r="24" fill="url(#hs-sunfill)" />
        </g>

        {/* voltage trace card */}
        <g transform="translate(26 26)">
          <rect className="hs-card" width="360" height="150" rx="16" />
          <text x="18" y="28" className="hs-label">{t('hero.voltage')}</text>
          <line x1="24" x2="336" y1="70" y2="70" stroke="#d96868" strokeWidth="1.5" strokeDasharray="5 5" />
          <text x="336" y="62" textAnchor="end" className="hs-limit">{t('hero.limit')}</text>
          <path className="hs-before" d={BEFORE} fill="none" stroke="url(#hs-trace)" strokeWidth="4" strokeLinecap="round" />
          <path className="hs-after" d={AFTER} fill="none" stroke="url(#hs-good)" strokeWidth="4" strokeLinecap="round" />
          <g className="hs-alert">
            <circle cx="196" cy="40" r="9" fill="#d96868" opacity="0.25" />
            <circle cx="196" cy="40" r="4.5" fill="#d96868" />
          </g>
          <g className="hs-ok" transform="translate(300 18)">
            <rect width="44" height="24" rx="12" fill="#689d4b" />
            <path d="M14 12.5l5 5 11-11" fill="none" stroke="#f2f2f2" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        </g>

        {/* the street: transformer, wire, homes with panels */}
        <line className="hs-ground" x1="40" x2="520" y1="338" y2="338" strokeWidth="2" />
        <g transform="translate(46 262)">
          <rect width="40" height="58" rx="9" fill="url(#hs-good)" />
          <rect x="8" y="12" width="24" height="5" rx="2.5" fill="#d2edd7" />
          <rect x="8" y="22" width="24" height="5" rx="2.5" fill="#d2edd7" opacity="0.7" />
          <rect x="8" y="32" width="24" height="5" rx="2.5" fill="#d2edd7" opacity="0.45" />
          <rect x="17" y="58" width="6" height="18" fill="#5d7a5e" />
        </g>
        <path d="M86 276 H470" stroke="#88a886" strokeWidth="3" />
        <path className="hs-flow" d="M470 276 H86" stroke="#e3a83f" strokeWidth="3.4" strokeLinecap="round" strokeDasharray="2 14" fill="none" />
        {HOUSES.map((x, i) => (
          <g key={x} transform={`translate(${x} 0)`}>
            <line x1="28" x2="28" y1="276" y2="294" stroke="#88a886" strokeWidth="2" />
            <path d="M0 312 L28 288 L56 312 V338 H0 Z" fill={i % 2 ? '#a9c8a6' : '#88a886'} />
            <rect x="22" y="318" width="12" height="20" rx="2" fill="#5d7a5e" opacity="0.6" />
            <path className="hs-panel" d="M8 306 L26 291 L36 299 L18 314 Z" />
          </g>
        ))}
      </svg>
    </figure>
  )
}
