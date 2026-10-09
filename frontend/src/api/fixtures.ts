/** Fixture mode (VITE_V2_FIXTURES=1): answer /api/v2 requests from hand-made samples in the plan's P8.3 shapes.
 *  The UI shows a "sample data" banner in this mode; the samples are replaced by Person A's fixtures and then the API. */
export async function loadFixture(url: string): Promise<unknown> {
  const { pathname, searchParams } = new URL(url, 'http://fixture')
  const route = pathname.replace(/^\/api\/v2/, '')
  const rule = searchParams.get('rule') ?? 'up_2005'
  switch (route) {
    case '/rules':
      return (await import('../fixtures/v2/rules_sample.json')).default.rules
    case '/risk':
      return { ...(await import('../fixtures/v2/risk_sample.json')).default, rule }
    case '/fixes':
      return rule === 'pm10'
        ? (await import('../fixtures/v2/fixes_safe_sample.json')).default
        : { ...(await import('../fixtures/v2/fixes_no_safe_sample.json')).default, rule }
    default:
      throw new Error(`no sample data for ${route}`)
  }
}
