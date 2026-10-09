import { lazy, Suspense, useState } from 'react'
import { LangProvider, useT } from '../i18n'
import type { Area } from './areas'
import { DEFAULT_RULE } from './defaults'
import { Shell } from './Shell'
import type { ViewProps } from './view'

const Home = lazy(() => import('../pages/Home'))
const Fixes = lazy(() => import('../pages/Fixes'))
const TryChange = lazy(() => import('../pages/TryChange'))
const Planning = lazy(() => import('../pages/Planning'))
const Proof = lazy(() => import('../pages/Proof'))

function Page({ area, view }: { area: Area; view: ViewProps }) {
  switch (area) {
    case 'home': return <Home {...view} />
    case 'try': return <TryChange {...view} />
    case 'fixes': return <Fixes {...view} />
    case 'planning': return <Planning {...view} />
    case 'proof': return <Proof />
  }
}

function Layout() {
  const t = useT()
  // One rule and one day for the whole dashboard, so switching ±6% to ±10% on Home carries over to Fixes.
  const [rule, setRule] = useState(DEFAULT_RULE)
  const [date, setDate] = useState<string | null>(null)
  const view: ViewProps = { rule, onRule: setRule, date, onDate: setDate }
  return (
    <Shell
      render={(area) => (
        <Suspense fallback={<div className="loading" role="status">{t('shell.loading')}</div>}>
          <Page area={area} view={view} />
        </Suspense>
      )}
    />
  )
}

export default function V2App() {
  return <LangProvider><Layout /></LangProvider>
}
