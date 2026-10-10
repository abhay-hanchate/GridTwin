import { useEffect, useState, type KeyboardEvent, type ReactNode } from 'react'
import { LANGS, useLang, useT, type StringKey } from '../i18n'
import { AREAS, type Area } from './areas'

const label = (area: Area) => `area.${area}` as StringKey
const fromHash = (): Area | null => {
  const id = window.location.hash.slice(1)
  return (AREAS as readonly string[]).includes(id) ? (id as Area) : null
}

type Props = {
  render: (area: Area, go: (area: Area) => void) => ReactNode
  initial?: Area
}

/** The layout: brand, the areas as WAI-ARIA tabs numbered in the order of the journey, language switch, one panel. */
export function Shell({ render, initial = 'home' }: Props) {
  // The URL hash names the area (#fixes), so a demo can link straight to a page.
  const [area, setAreaState] = useState<Area>(() => fromHash() ?? initial)
  const setArea = (id: Area) => {
    setAreaState(id)
    history.replaceState(null, '', `#${id}`)
  }
  const { lang, setLang } = useLang()
  const t = useT()

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
          <img className="brand-mark" src="/favicon.svg" alt="" />
          <div>
            <h1>GridTwin</h1>
          </div>
        </div>
        <div className="lang-switch segmented" role="group" aria-label={t('shell.language')}>
          {LANGS.map((l) => (
            <button key={l.id} lang={l.id} aria-pressed={lang === l.id}
              className={`seg ${lang === l.id ? 'active' : ''}`} onClick={() => setLang(l.id)}>{l.label}</button>
          ))}
        </div>
        <nav className="areas" aria-label={t('shell.areas')}>
          <div className="tabs" role="tablist" aria-label={t('shell.areas')}>
            {AREAS.map((id) => (
              <button key={id} id={`area-${id}`} role="tab" aria-selected={area === id} aria-controls="panel"
                tabIndex={area === id ? 0 : -1} className={`tab ${area === id ? 'active' : ''}`}
                onClick={() => setArea(id)} onKeyDown={onTabKey}>
                {id !== 'home' && <span className="step-no" aria-hidden="true">{AREAS.indexOf(id)}</span>}
                {t(label(id))}
              </button>
            ))}
          </div>
        </nav>
      </header>
      <main id="content" tabIndex={-1}>
        <div id="panel" role="tabpanel" aria-labelledby={`area-${area}`}>{render(area, setArea)}</div>
      </main>
      <footer className="footer">{t('shell.footer')}</footer>
    </div>
  )
}
