import gsap from 'gsap'
import { Plug, Sun } from 'lucide-react'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { one } from '../../format'
import { useT } from '../../i18n'
import { reducedMotion, useNarrow } from './anim'
import { PHASES } from './balance'
import { landscape, portrait, type Phase, type Slot } from './streetGeo'
import { homeClass } from './voltage'

/** The street as a map: the transformer on its pole, three phase feeders fanning out from it, and every home drawn
 *  on the phase it is connected to, in order along the wire. Current flows along each wire the way the power goes:
 *  amber back towards the transformer when solar is exported, blue towards the homes when they draw. */

const EXPORT = '#f59e0b'
const IMPORT = '#0ea5e9'
const IDLE = 0.02                // kW below which a wire is shown still

export interface HomeNow {
  v: number | null
  solar: number
  demand: number
  net: number                     // + drawing, - sending back
}

type Props = {
  phase: Phase[]                  // each home's phase
  dist: number[]                  // each home's hops from the transformer
  kwp: number[]
  now: HomeNow[]
  phaseKw: [number, number, number]
  grid: number                    // kW at the transformer, + drawn
  scale: { phase: number; home: number; grid: number }
  limits: { min: number; max: number }
  trafoKva: number
  loadingPct: number
  selected: number | null
  onHome: (h: number | null) => void
  label: string
}

function House({ s, kwp, now, limits, sel, onHome, panelGlow }: {
  s: Slot; kwp: number; now: HomeNow; limits: { min: number; max: number }; sel: boolean; onHome: (h: number | null) => void; panelGlow: number
}) {
  const { x, top } = s
  const cls = homeClass(now.v, limits)
  const exporting = now.net < -IDLE
  return (
    <g className={`sv-house ${cls} ${sel ? 'sel' : ''} ${exporting ? 'exporting' : ''}`} data-home={s.h}
      onClick={(e) => { e.stopPropagation(); onHome(sel ? null : s.h) }}>
      <circle className="sv-halo" cx={x} cy={top + 20} r={17} />
      {sel && <rect className="sv-sel" x={x - 23} y={top - 7} width={46} height={50} rx={10} />}
      <path className="sv-roof" d={`M${x - 18},${top + 15} L${x},${top} L${x + 18},${top + 15} Z`} />
      <rect className="sv-wall" x={x - 13} y={top + 14} width={26} height={22} rx={1.5} />
      <rect className="sv-window" x={x - 9.5} y={top + 19} width={7} height={6.5} rx={1} />
      <rect className="sv-door" x={x + 2.5} y={top + 23} width={6.5} height={13} rx={1} />
      {kwp > 0 && (
        <g className="sv-panel">
          <path d={`M${x - 14.6},${top + 11.6} L${x - 5.4},${top + 4} L${x - 2.9},${top + 7.1} L${x - 12.1},${top + 14.7} Z`} />
          <path className="sv-panel-glow" style={{ opacity: panelGlow }}
            d={`M${x - 14.6},${top + 11.6} L${x - 5.4},${top + 4} L${x - 2.9},${top + 7.1} L${x - 12.1},${top + 14.7} Z`} />
        </g>
      )}
      <rect className="sv-hit" x={x - 22} y={top - 6} width={44} height={48} />
    </g>
  )
}
const MemoHouse = memo(House)

function StreetView({ phase, dist, kwp, now, phaseKw, grid, scale, limits, trafoKva, loadingPct, selected, onHome, label }: Props) {
  const t = useT()
  const root = useRef<SVGSVGElement>(null)
  const wrap = useRef<HTMLDivElement>(null)
  const narrow = useNarrow()
  const g = useMemo(() => (narrow ? portrait : landscape)(phase, dist), [narrow, phase, dist])
  const { W, H, tx: TX, ty: TY, slots } = g
  const feeders = useRef<(SVGPathElement | null)[]>([])
  const drops = useRef<(SVGPathElement | null)[]>([])
  const gridFlow = useRef<SVGPathElement>(null)
  const [hover, setHover] = useState<number | null>(null)

  // signed speeds (px/s along each path, + towards the homes) for the ticker; written after every render
  const speeds = useRef({ feeders: [0, 0, 0], drops: [] as number[], grid: 0 })
  const speed = (kw: number, max: number) => {
    if (Math.abs(kw) < IDLE) return 0
    return Math.sign(kw) * (12 + 52 * Math.sqrt(Math.min(1, Math.abs(kw) / Math.max(0.1, max))))
  }
  useEffect(() => {
    speeds.current = {
      feeders: phaseKw.map((kw) => speed(kw, scale.phase)),
      drops: now.map((n) => speed(n.net, scale.home)),
      grid: speed(grid, scale.grid),
    }
  })

  // one GSAP ticker moves the current on every wire; it stops while the map is off screen
  useEffect(() => {
    if (reducedMotion()) return
    let visible = true
    const io = typeof IntersectionObserver !== 'undefined'
      ? new IntersectionObserver(([e]) => { visible = e.isIntersecting }) : undefined
    if (wrap.current) io?.observe(wrap.current)
    const offs = { feeders: [0, 0, 0], drops: [] as number[], grid: 0 }
    const tick = (_: number, deltaMs: number) => {
      if (!visible) return
      const dt = Math.min(0.05, deltaMs / 1000)
      const sp = speeds.current
      feeders.current.forEach((el, i) => {
        if (!el) return
        offs.feeders[i] += sp.feeders[i] * dt
        el.setAttribute('stroke-dashoffset', String(-offs.feeders[i]))
      })
      drops.current.forEach((el, i) => {
        if (!el) return
        offs.drops[i] = (offs.drops[i] ?? 0) + (sp.drops[i] ?? 0) * dt * 0.5
        el.setAttribute('stroke-dashoffset', String(-offs.drops[i]))
      })
      if (gridFlow.current) {
        offs.grid += sp.grid * dt
        gridFlow.current.setAttribute('stroke-dashoffset', String(-offs.grid))
      }
    }
    gsap.ticker.add(tick)
    return () => { gsap.ticker.remove(tick); io?.disconnect() }
  }, [])

  // houses rise into place once; homes outside the rule pulse
  useEffect(() => {
    if (reducedMotion() || !root.current) return
    const ctx = gsap.context(() => {
      gsap.from('.sv-house', { opacity: 0, y: 10, duration: 0.5, ease: 'back.out(2)', stagger: { each: 0.006, from: 'start' } })
      gsap.from('.sv-feeder-base', { strokeDashoffset: 1400, strokeDasharray: 1400, duration: 1.1, ease: 'power2.out' })
      gsap.fromTo('.sv-halo', { scale: 0.8, opacity: 0.4 }, { scale: 1.45, opacity: 0, duration: 1.8, ease: 'sine.out', repeat: -1, transformOrigin: '50% 50%', stagger: { each: 0.07, from: 'random', repeat: -1 } })
      gsap.to('.sv-trafo-glow', { scale: 1.12, duration: 1.6, ease: 'sine.inOut', repeat: -1, yoyo: true, transformOrigin: '50% 50%' })
    }, root)
    return () => ctx.revert()
  }, [])

  const tip = hover !== null ? slots[hover] : null
  const tipNow = hover !== null ? now[hover] : null
  const exporting = grid < -IDLE

  return (
    <div ref={wrap} className="sv-wrap">
      <div className="sv-scroll">
        <svg ref={root} className={`sv ${narrow ? 'portrait' : ''}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} onClick={() => onHome(null)}>
          <defs>
            <radialGradient id="sv-glow-back"><stop offset="0" stopColor={EXPORT} stopOpacity="0.55" /><stop offset="1" stopColor={EXPORT} stopOpacity="0" /></radialGradient>
            <radialGradient id="sv-glow-draw"><stop offset="0" stopColor={IMPORT} stopOpacity="0.45" /><stop offset="1" stopColor={IMPORT} stopOpacity="0" /></radialGradient>
            <linearGradient id="sv-trafo" x1="0" x2="1"><stop offset="0" stopColor="#3b4a63" /><stop offset="0.5" stopColor="#56677f" /><stop offset="1" stopColor="#2c3a50" /></linearGradient>
          </defs>

          {/* lanes: a soft strip behind each phase's homes */}
          {PHASES.map((p) => (
            <rect key={p} className={`sv-lane lane-${p.toLowerCase()}`} x={g.lane[p].x} y={g.lane[p].y} width={g.lane[p].w} height={g.lane[p].h} rx={22} />
          ))}

          {/* the grid feeding the transformer */}
          <path className="sv-grid-base" d={g.grid.path} />
          <path ref={gridFlow} className={`sv-flow grid ${Math.abs(grid) < IDLE ? 'idle' : exporting ? 'back' : 'draw'}`} d={g.grid.path} />
          <text className="sv-grid-label" x={g.grid.label.x} y={g.grid.label.y}>{t('sv.grid')}</text>
          <text className={`sv-grid-kw ${exporting ? 'back' : 'draw'}`} x={g.grid.label.x} y={g.grid.label.y + 32}>
            {Math.abs(grid) < IDLE ? '0 kW' : `${exporting ? '←' : '→'} ${one(Math.abs(grid))} kW`}
          </text>

          {/* phase feeders: the wire, then the current moving on it */}
          {PHASES.map((p, i) => {
            const kw = phaseKw[i]
            const mag = Math.min(1, Math.abs(kw) / Math.max(0.1, scale.phase))
            const dir = Math.abs(kw) < IDLE ? 'idle' : kw < 0 ? 'back' : 'draw'
            const lb = g.label[p]
            return (
              <g key={p}>
                <path className={`sv-feeder-base ph-${p.toLowerCase()}`} d={g.feeder[p]} />
                <path ref={(el) => { feeders.current[i] = el }} className={`sv-flow feeder ${dir}`} d={g.feeder[p]}
                  strokeWidth={2 + 4.5 * mag} />
                <g className={`sv-phase-label ${dir}`}>
                  <circle r={12} className={`ph-dot ph-${p.toLowerCase()}`} cx={lb.cx} cy={lb.cy} />
                  <text className="ph-letter" x={lb.cx} y={lb.cy + 4.5} textAnchor="middle">{p}</text>
                  <text className="ph-kw" x={lb.tx} y={lb.ty} textAnchor={lb.anchor}>
                    {dir === 'idle' ? '0 kW' : `${g.arrow[dir]} ${one(Math.abs(kw))} kW`}
                  </text>
                </g>
              </g>
            )
          })}

          {/* service drops: each home's own wire to its phase */}
          {slots.map((s) => {
            const n = now[s.h]
            const dir = Math.abs(n.net) < IDLE ? 'idle' : n.net < 0 ? 'back' : 'draw'
            return (
              <g key={`d${s.h}`}>
                <path className={`sv-drop ph-${phase[s.h].toLowerCase()}`} d={s.drop} />
                <path ref={(el) => { drops.current[s.h] = el }} className={`sv-flow drop ${dir}`} d={s.drop} />
                <circle className={`sv-tap ph-${phase[s.h].toLowerCase()}`} cx={s.tap.x} cy={s.tap.y} r={2.6} />
              </g>
            )
          })}

          {/* the transformer on its pole */}
          <g className={`sv-trafo ${exporting ? 'back' : 'draw'}`}>
            <circle className="sv-trafo-glow" cx={TX} cy={TY} r={78} fill={`url(#sv-glow-${exporting ? 'back' : 'draw'})`} />
            <rect className="sv-pole" x={TX - 4} y={g.pole.top} width={8} height={g.pole.bottom - g.pole.top} rx={3} />
            <rect className="sv-arm" x={TX - 30} y={TY - 52} width={60} height={6} rx={2} />
            <rect x={TX - 30} y={TY - 40} width={60} height={80} rx={10} fill="url(#sv-trafo)" />
            {[-16, -6, 4, 14].map((dx) => <rect key={dx} className="sv-fin" x={TX + dx - 2} y={TY - 32} width={4} height={56} rx={2} />)}
            <rect className="sv-plate" x={g.plate.x - 28} y={g.plate.y - 10} width={56} height={20} rx={5} />
            <text className="sv-plate-text" x={g.plate.x} y={g.plate.y + 4} textAnchor="middle">{Math.round(trafoKva)} kVA</text>
            <text className="sv-load" x={g.load.x} y={g.load.y} textAnchor="middle">{t('sv.load', { pct: Math.round(loadingPct) })}</text>
          </g>

          {slots.map((s) => (
            <MemoHouse key={s.h} s={s} kwp={kwp[s.h]} now={now[s.h]} limits={limits} sel={selected === s.h} onHome={onHome}
              panelGlow={kwp[s.h] > 0 ? Math.min(1, now[s.h].solar / kwp[s.h] / 0.75) : 0} />
          ))}
          {/* hover targets on top so the tooltip follows the pointer house by house */}
          {slots.map((s) => (
            <rect key={`h${s.h}`} className="sv-hover" x={s.x - 22} y={s.top - 6} width={44} height={48}
              onPointerEnter={() => setHover(s.h)} onPointerLeave={() => setHover((h) => (h === s.h ? null : h))}
              onClick={(e) => { e.stopPropagation(); onHome(selected === s.h ? null : s.h) }} />
          ))}
        </svg>
        {tip && tipNow && (
          <div className="sv-tip" style={{ left: `${(tip.x / W) * 100}%`, top: `${((tip.tipAbove ? tip.top - 8 : tip.top + 50) / H) * 100}%` }}
            data-up={tip.tipAbove}>
            <b>{t('player.home_detail', { home: tip.h + 1 })}</b> · {t('player.home_phase')} {phase[tip.h]} ·{' '}
            {tipNow.v === null ? '—' : `${one(tipNow.v)} V`}
            <br /><Sun size={12} className="i" /> {one(tipNow.solar)} kW · <Plug size={12} className="i" /> {one(tipNow.demand)} kW ·{' '}
            <span className={tipNow.net < 0 ? 'back' : 'draw'}>{tipNow.net < 0 ? t('sv.sends', { kw: one(-tipNow.net) }) : t('sv.draws', { kw: one(tipNow.net) })}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default memo(StreetView)
