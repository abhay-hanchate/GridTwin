import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(import.meta.dirname, '..')
const shipped = (dir: string): string[] => readdirSync(dir).flatMap((name) => {
  const path = join(dir, name)
  if (statSync(path).isDirectory()) return name === 'fixtures' ? [] : shipped(path)
  return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : []
})

describe('the dashboard is v2 only (P10.12)', () => {
  it('no shipped code calls a Round 1 /api route', () => {
    const legacy = shipped(SRC).filter((f) => /['"`]\/api\/(?!v2)/.test(readFileSync(f, 'utf-8')))
    expect(legacy.map((f) => relative(SRC, f))).toEqual([])
  })

  it('the entry point renders the v2 dashboard without a build switch', () => {
    const main = readFileSync(join(SRC, 'main.tsx'), 'utf-8')
    expect(main).toContain('<V2App />')
    expect(main).not.toMatch(/VITE_DASHBOARD|V2_DASHBOARD|<App \/>/)
  })
})
