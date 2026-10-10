import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useT } from '../i18n'

type Theme = 'light' | 'dark'
const KEY = 'gridtwin.theme'

function systemTheme(): Theme {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function storedTheme(): Theme | null {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : null
  } catch {
    return null
  }
}

/** Light or dark. Follows the device until the user picks one; the pick is remembered on this browser. */
export default function ThemeToggle() {
  const t = useT()
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? systemTheme())
  useEffect(() => {
    if (storedTheme() || theme !== systemTheme()) document.documentElement.dataset.theme = theme
  }, [theme])
  const flip = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    document.documentElement.dataset.theme = next
    try { localStorage.setItem(KEY, next) } catch { /* the choice just is not kept */ }
  }
  return (
    <button type="button" className="theme-toggle" onClick={flip} aria-label={t(theme === 'dark' ? 'shell.theme_light' : 'shell.theme_dark')}
      title={t(theme === 'dark' ? 'shell.theme_light' : 'shell.theme_dark')}>
      {theme === 'dark' ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
    </button>
  )
}
