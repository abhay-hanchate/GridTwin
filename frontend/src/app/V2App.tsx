import { lazy, Suspense, useState } from 'react'
import { FIXTURES } from '../api/v2'
import { LangProvider, useT } from '../i18n'
import type { Area } from './areas'
import { DEFAULT_RULE } from './defaults'
import { Shell } from './Shell'

const Home = lazy(() => import('../pages/Home'))
const Fixes = lazy(() => import('../pages/Fixes'))
// Areas without a v2 page yet show their Round 1 screen, which still talks to the legacy API, so the v2 layout is
// always demonstrable.
const GridView = lazy(() => import('../components/GridView'))
const CapacityView = lazy(() => import('../components/CapacityView'))
const ForecastView = lazy(() => import('../components/ForecastView'))

function Page({ area, rule, onRule }: { area: Area; rule: string; onRule: (id: string) => void }) {
  switch (area) {
    case 'home': return <Home rule={rule} onRule={onRule} />
    case 'try': return <GridView scenario="S4" />
    case 'fixes': return <Fixes rule={rule} onRule={onRule} />
    case 'planning': return <CapacityView />
    case 'proof': return <ForecastView />
  }
}

function Layout() {
  const t = useT()
  // One rule for the whole dashboard, so switching ±6% to ±10% on Home carries over to Fixes.
  const [rule, setRule] = useState(DEFAULT_RULE)
  return (
    <Shell
      banner={FIXTURES ? <p className="fixture-banner" role="note">{t('shell.fixtures')}</p> : null}
      render={(area) => (
        <Suspense fallback={<div className="loading" role="status">{t('shell.loading')}</div>}>
          <Page area={area} rule={rule} onRule={setRule} />
        </Suspense>
      )}
    />
  )
}

export default function V2App() {
  return <LangProvider><Layout /></LangProvider>
}
