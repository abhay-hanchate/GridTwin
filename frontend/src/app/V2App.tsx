import { lazy, Suspense } from 'react'
import { FIXTURES } from '../api/v2'
import { LangProvider, useT } from '../i18n'
import type { Area } from './areas'
import { Shell } from './Shell'

// Until an area's v2 page exists it shows the Round 1 screen, which still talks to the legacy API, so the
// v2 layout is always demonstrable.
const StoryView = lazy(() => import('../components/StoryView'))
const GridView = lazy(() => import('../components/GridView'))
const FixesView = lazy(() => import('../components/FixesView'))
const CapacityView = lazy(() => import('../components/CapacityView'))
const ForecastView = lazy(() => import('../components/ForecastView'))

const LEGACY_TAB_TO_AREA = { grid: 'try', fixes: 'fixes', forecast: 'proof' } as const

function Page({ area, go }: { area: Area; go: (area: Area) => void }) {
  switch (area) {
    case 'home': return <StoryView go={(tab) => go(LEGACY_TAB_TO_AREA[tab])} />
    case 'try': return <GridView scenario="S4" />
    case 'fixes': return <FixesView scenario="S4" />
    case 'planning': return <CapacityView />
    case 'proof': return <ForecastView />
  }
}

function Layout() {
  const t = useT()
  return (
    <Shell
      banner={FIXTURES ? <p className="fixture-banner" role="note">{t('shell.fixtures')}</p> : null}
      render={(area, go) => (
        <Suspense fallback={<div className="loading" role="status">{t('shell.loading')}</div>}>
          <Page area={area} go={go} />
        </Suspense>
      )}
    />
  )
}

export default function V2App() {
  return <LangProvider><Layout /></LangProvider>
}
