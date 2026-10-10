import { lazy, Suspense, useEffect, useState } from 'react'
import { LangProvider, useT } from '../i18n'
import type { Area } from './areas'
import { DEFAULT_RULE } from './defaults'
import { Shell } from './Shell'
import type { ViewProps } from './view'

const pages = {
  overview: () => import('../pages/Overview'), forecast: () => import('../pages/Forecast'), fixes: () => import('../pages/Fixes'),
  try: () => import('../pages/TryChange'), planning: () => import('../pages/Planning'),
}
const Overview = lazy(pages.overview)
const Forecast = lazy(pages.forecast)
const Fixes = lazy(pages.fixes)
const TryChange = lazy(pages.try)
const Planning = lazy(pages.planning)

/** After the first page shows, fetch the other pages' code in the background so every step opens at once. */
function usePreloadPages() {
  useEffect(() => {
    const load = () => Object.values(pages).forEach((p) => { p().catch(() => undefined) })
    const id = setTimeout(load, 1500)
    return () => clearTimeout(id)
  }, [])
}

function Page({ area, view, go }: { area: Area; view: ViewProps; go: (area: Area) => void }) {
  switch (area) {
    case 'home': return <Overview {...view} go={go} />
    case 'forecast': return <Forecast {...view} go={go} />
    case 'try': return <TryChange {...view} go={go} />
    case 'fixes': return <Fixes {...view} go={go} />
    case 'planning': return <Planning {...view} go={go} />
  }
}

// The day and rule are kept for the browser tab, so a reload or a link to #fixes stays on the day being looked at.
const STORE = 'gridtwin.view'
function stored(): { rule: string; date: string | null } {
  try {
    const v = JSON.parse(sessionStorage.getItem(STORE) ?? '{}') as { rule?: unknown; date?: unknown }
    return { rule: typeof v.rule === 'string' ? v.rule : DEFAULT_RULE, date: typeof v.date === 'string' ? v.date : null }
  } catch {
    return { rule: DEFAULT_RULE, date: null }
  }
}

function Layout() {
  const t = useT()
  usePreloadPages()
  // One rule and one day for the whole dashboard, so switching ±6% to ±10% on Home carries over to Fixes.
  const [rule, setRule] = useState(() => stored().rule)
  const [date, setDate] = useState<string | null>(() => stored().date)
  useEffect(() => {
    try { sessionStorage.setItem(STORE, JSON.stringify({ rule, date })) } catch { /* the choice just is not kept */ }
  }, [rule, date])
  const view: ViewProps = { rule, onRule: setRule, date, onDate: setDate }
  return (
    <Shell
      render={(area, go) => (
        <Suspense fallback={<div className="loading" role="status">{t('shell.loading')}</div>}>
          <Page area={area} view={view} go={go} />
        </Suspense>
      )}
    />
  )
}

export default function V2App() {
  return <LangProvider><Layout /></LangProvider>
}
