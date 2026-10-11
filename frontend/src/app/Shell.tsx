import { CloudSun, FileCheck2, FlaskConical, Gauge, LayoutDashboard, Map as MapIcon, Rocket, Wrench, type LucideIcon } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import ThemeToggle from '../components/ThemeToggle'
import { LANGS, useLang, useT, type StringKey } from '../i18n'
import { AREAS, type Area } from './areas'

const label = (area: Area) => `area.${area}` as StringKey
const ICONS: Record<Area, LucideIcon> = {
  home: LayoutDashboard, forecast: CloudSun, fixes: Wrench, planning: MapIcon, try: FlaskConical, control: Gauge, surrogate: Rocket, evidence: FileCheck2,
}
const fromHash = (): Area | null => {
  const id = window.location.hash.slice(1)
  return (AREAS as readonly string[]).includes(id) ? (id as Area) : null
}

type Props = {
  render: (area: Area, go: (area: Area) => void) => ReactNode
  initial?: Area
  /** A thin bar under the header for this area (the day, rule and status), or nothing. */
  context?: (area: Area) => ReactNode
}

/** The layout: brand, the areas as WAI-ARIA tabs numbered in the order of the journey, language switch, one panel. */
export function Shell({ render, initial = 'home', context }: Props) {
  // The URL hash names the area (#fixes), so a demo can link straight to a page.
  const [area, setAreaState] = useState<Area>(() => fromHash() ?? initial)
  const setArea = (id: Area) => {
    setAreaState(id)
    history.replaceState(null, '', `#${id}`)
  }
  const { lang, setLang } = useLang()
  const t = useT()
  // the green highlight slides to the active tab
  const tabsRef = useRef<HTMLDivElement>(null)
  const [glide, setGlide] = useState<{ left: number; width: number } | null>(null)
  useLayoutEffect(() => {
    const measure = () => {
      const el = tabsRef.current?.querySelector<HTMLElement>('.tab.active')
      if (el) setGlide({ left: el.offsetLeft, width: el.offsetWidth })
    }
    measure()
    // tab widths change when the web font arrives and when the row resizes, so measure again then
    let alive = true
    document.fonts?.ready.then(() => { if (alive) measure() })
    const ro = typeof ResizeObserver === 'function' && tabsRef.current ? new ResizeObserver(measure) : null
    if (ro && tabsRef.current) { tabsRef.current.querySelectorAll('.tab').forEach((el) => ro.observe(el)) }
    window.addEventListener('resize', measure)
    return () => { alive = false; ro?.disconnect(); window.removeEventListener('resize', measure) }
  }, [area, lang])

  useEffect(() => { document.title = `${t(label(area))} · GridTwin` }, [area, t])

  // Arrow keys move between tabs, Home/End jump to the ends.
  const onTabKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = AREAS.indexOf(area)
    const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: AREAS.length - 1 }[e.key]
    if (next === undefined) return
    e.preventDefault()
    const id = AREAS[(next + AREAS.length) % AREAS.length]
    setArea(id)
    document.getElementById(`area-${id}`)?.focus()
  }

  return (
    <div className="app">
      <a className="skip-link" href="#content">{t('shell.skip')}</a>
      <header className="header">
        <div className="brand">
          <img className="brand-mark" src="/favicon.svg?v=2" alt="" />
          <div>
            <h1>GridTwin</h1>
          </div>
        </div>
        <ThemeToggle />
        <div className="lang-switch segmented" role="group" aria-label={t('shell.language')}>
          {LANGS.map((l) => (
            <button key={l.id} lang={l.id} aria-pressed={lang === l.id}
              className={`seg ${lang === l.id ? 'active' : ''}`} onClick={() => setLang(l.id)}>{l.label}</button>
          ))}
        </div>
        <nav className="areas" aria-label={t('shell.areas')}>
          <div className="tabs" role="tablist" aria-label={t('shell.areas')} ref={tabsRef}>
            {glide && <span className="tab-glide" aria-hidden="true" style={{ transform: `translateX(${glide.left}px)`, width: glide.width }} />}
            {AREAS.map((id) => (
              <button key={id} id={`area-${id}`} role="tab" aria-selected={area === id} aria-controls="panel"
                tabIndex={area === id ? 0 : -1} className={`tab ${area === id ? 'active' : ''}`} title={t(label(id))}
                onClick={() => setArea(id)} onKeyDown={onTabKey}>
                {(() => { const Icon = ICONS[id]; return <Icon className="tab-icon" size={16} strokeWidth={2.1} aria-hidden="true" /> })()}
                <span className="tab-label">{t(label(id))}</span>
              </button>
            ))}
          </div>
        </nav>
        {context?.(area)}
      </header>
      <main id="content" tabIndex={-1}>
        <div id="panel" role="tabpanel" aria-labelledby={`area-${area}`}>{render(area, setArea)}</div>
      </main>
      <footer className="footer">{t('shell.footer')}</footer>
    </div>
  )
}
