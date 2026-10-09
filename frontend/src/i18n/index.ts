import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import en from './en.json'
import hi from './hi.json'

export type Lang = 'en' | 'hi'
export type StringKey = keyof typeof en
export type Vars = Record<string, string | number>

export const LANGS: { id: Lang; label: string }[] = [{ id: 'en', label: 'English' }, { id: 'hi', label: 'हिन्दी' }]
// Typed this way so a key missing from hi.json is a compile error, not a blank label.
const DICTS: Record<Lang, Record<StringKey, string>> = { en, hi }
const STORAGE_KEY = 'gridtwin.lang'

/** The string for `key` with every `{name}` replaced from `vars`. Numbers always arrive through `vars`. */
export function translate(lang: Lang, key: StringKey, vars?: Vars): string {
  const template = DICTS[lang][key] ?? en[key]
  if (!vars) return template
  return template.replace(/\{([a-z_]+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole))
}

function storedLang(): Lang {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'hi' ? 'hi' : 'en'
  } catch {
    return 'en'   // private windows and blocked storage fall back to English
  }
}

const LangContext = createContext<{ lang: Lang; setLang: (lang: Lang) => void }>({ lang: 'en', setLang: () => {} })

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(storedLang)
  useEffect(() => { document.documentElement.lang = lang }, [lang])
  const value = useMemo(() => ({
    lang,
    setLang: (next: Lang) => {
      setLangState(next)
      try { localStorage.setItem(STORAGE_KEY, next) } catch { /* the choice just is not remembered */ }
    },
  }), [lang])
  return createElement(LangContext.Provider, { value }, children)
}

export const useLang = () => useContext(LangContext)

export function useT() {
  const { lang } = useLang()
  return useCallback((key: StringKey, vars?: Vars) => translate(lang, key, vars), [lang])
}
