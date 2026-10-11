import { CloudSun, FileCheck2, FlaskConical, Gauge, LayoutDashboard, Map as MapIcon, Rocket, Wrench, type LucideIcon } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import ThemeToggle from '../components/ThemeToggle'
import { LANGS, useLang, useT, type StringKey } from '../i18n'
import { AREAS, type Area } from './areas'

const label = (area: Area) => `area.${area}` as StringKey
const question = (area: Area) => (area === 'home' || area === 'evidence' ? `menu.q_${area}` : `overview.q_${area}`) as StringKey
const ICONS: Record<Area, LucideIcon> = {
  home: LayoutDashboard, forecast: CloudSun, fixes: Wrench, planning: MapIcon, try: FlaskConical, control: Gauge, surrogate: Rocket, evidence: FileCheck2,
}
const fromHash = (): Area | null => {
  const id = window.location.hash.slice(1)
  return (AREAS as readonly string[]).includes(id) ? (id as Area) : null
}
const two = (n: number) => String(n).padStart(2, '0')

type Props = {
  render: (area: Area, go: (area: Area) => void) => ReactNode
  initial?: Area
  /** A thin bar under the header for this area (the day, rule and status), or nothing. */
  context?: (area: Area) => ReactNode
}

/** The layout: brand, a Menu button that opens a full-screen menu of every step (WAI-ARIA tabs inside it), the theme
 *  and language switches, the context bar, and one panel. Picking a step closes the menu and switches the page. */
export function Shell({ render, initial = 'home', context }: Props) {
  // The URL hash names the area (#fixes), so a demo can link straight to a page.
  const [area, setAreaState] = useState<Area>(() => fromHash() ?? initial)
  const [open, setOpen] = useState(false)
  const [hover, setHover] = useState<Area | null>(null)
  const menuBtn = useRef<HTMLButtonElement>(null)
  const { lang, setLang } = useLang()
  const t = useT()

  const setArea = (id: Area) => {
    setAreaState(id)
    history.replaceState(null, '', `#${id}`)
  }
  const pick = (id: Area) => {
    setArea(id)
    setOpen(false)
    if (typeof window.scrollTo === 'function') try { window.scrollTo({ top: 0 }) } catch { /* jsdom */ }
  }

  useEffect(() => { document.title = `${t(label(area))} · GridTwin` }, [area, t])

  // While the menu is open: no page scroll behind it, Escape closes it, focus starts on the current step.
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    const id = window.setTimeout(() => document.getElementById(`area-${area}`)?.focus(), 60)
    const button = menuBtn.current
    return () => {
      document.body.style.overflow = prev
      window.removeEventListener('keydown', onKey)
      window.clearTimeout(id)
      button?.focus()
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // Arrow keys move between steps, Home/End jump to the ends.
  const onTabKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = AREAS.indexOf(area)
    const next = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: AREAS.length - 1 }[e.key]
    if (next === undefined) return
    e.preventDefault()
    const id = AREAS[(next + AREAS.length) % AREAS.length]
    setArea(id)
    document.getElementById(`area-${id}`)?.focus()
  }

  const shown = hover ?? area
  const ShownIcon = ICONS[shown]
  const CurrentIcon = ICONS[area]

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
        <button type="button" className="current-step" onClick={() => setOpen(true)} aria-hidden="true" tabIndex={-1}>
          <CurrentIcon size={16} strokeWidth={2.1} aria-hidden="true" />
          <span className="cs-no num">{two(AREAS.indexOf(area))}</span>
          <span className="cs-label">{t(label(area))}</span>
        </button>
        <ThemeToggle />
        <div className="lang-switch segmented" role="group" aria-label={t('shell.language')}>
          {LANGS.map((l) => (
            <button key={l.id} lang={l.id} aria-pressed={lang === l.id}
              className={`seg ${lang === l.id ? 'active' : ''}`} onClick={() => setLang(l.id)}>{l.label}</button>
          ))}
        </div>
        <button ref={menuBtn} type="button" className={`menu-btn ${open ? 'is-open' : ''}`} aria-expanded={open} aria-controls="site-menu"
          onClick={() => setOpen((o) => !o)}>
          <span className="menu-lines" aria-hidden="true"><i /><i /></span>
          <span className="menu-word">{t(open ? 'shell.close' : 'shell.menu')}</span>
        </button>
        {context?.(area)}
      </header>

      <div id="site-menu" className={`site-menu ${open ? 'open' : ''}`} inert={!open}>
        <div className="sm-inner">
          <nav className="sm-list" aria-label={t('shell.areas')}>
            <div role="tablist" aria-label={t('shell.areas')} aria-orientation="vertical">
              {AREAS.map((id, i) => {
                const Icon = ICONS[id]
                return (
                  <button key={id} id={`area-${id}`} role="tab" aria-selected={area === id} aria-controls="panel"
                    tabIndex={area === id ? 0 : -1} className={`sm-item ${area === id ? 'active' : ''}`} style={{ ['--i' as string]: i }}
                    onClick={() => pick(id)} onKeyDown={onTabKey} onMouseEnter={() => setHover(id)} onFocus={() => setHover(id)}
                    onMouseLeave={() => setHover(null)}>
                    <span className="sm-no num" aria-hidden="true">{two(i)}</span>
                    <Icon className="sm-icon" size={22} strokeWidth={1.9} aria-hidden="true" />
                    <span className="sm-text">
                      <span className="sm-title">{t(label(id))}</span>
                      <span className="sm-q" aria-hidden="true">{t(question(id))}</span>
                    </span>
                    <span className="sm-arrow" aria-hidden="true">→</span>
                  </button>
                )
              })}
            </div>
          </nav>
          <aside className="sm-side" aria-hidden="true">
            <div className="sm-big-icon" key={shown}><ShownIcon size={120} strokeWidth={1.1} /></div>
            <p className="sm-side-no num">{two(AREAS.indexOf(shown))} / {two(AREAS.length - 1)}</p>
            <p className="sm-side-title">{t(label(shown))}</p>
            <p className="sm-side-q">{t(question(shown))}</p>
          </aside>
        </div>
      </div>

      <main id="content" tabIndex={-1}>
        <div id="panel" role="tabpanel" aria-labelledby={`area-${area}`}>{render(area, pick)}</div>
      </main>
      <footer className="footer">{t('shell.footer')}</footer>
    </div>
  )
}
