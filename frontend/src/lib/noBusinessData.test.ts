import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * The frontend holds no business data. Machines, parts, prices, stock, suppliers, dealers, customers, orders, delivery and
 * recommendations all come from the backend, which reads them from the Noordveld graph. This test fails if any of those values
 * is written into frontend source code (tests and generated build output are excluded).
 */
const root = join(__dirname, '..', '..')
const SOURCE_DIRS = ['src', 'agentic-commerce/src', 'agentic-commerce/remotion']

const walk = (dir: string): string[] =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? walk(path) : [path]
  })

const files = SOURCE_DIRS.flatMap((d) => walk(join(root, d))).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\.tsx?$/.test(f))

const FORBIDDEN: [string, RegExp][] = [
  ['part number', /NVM-\d{4}/],
  ['machine model code', /\b(NV|KFT|BTS)-\d{3,4}\b/],
  ['graph record id', /\b(PRT|CUS|SUP|DLR|WH|ORD|SHP|ASM|MCH)-\d{2,4}\b/],
  ['price', /€\s?\d|\d\s?€|\bEUR\s?\d/],
  ['demo record name', /[A-Z][A-Za-z]+ \(demo\)/],
]

describe('frontend source holds no business data', () => {
  it('scans every frontend source file', () => {
    expect(files.length).toBeGreaterThan(80)
  })

  it.each(files.map((f) => relative(root, f).replace(/\\/g, '/')))('%s', (file) => {
    const text = readFileSync(join(root, file), 'utf8')
    for (const [what, pattern] of FORBIDDEN) {
      const hit = pattern.exec(text)
      expect(hit, `${file} contains a hardcoded ${what}: "${hit?.[0]}"`).toBeNull()
    }
  })

  it('has no generated catalogue or film dataset in the frontend', () => {
    const names = files.map((f) => relative(root, f).replace(/\\/g, '/'))
    expect(names.filter((n) => /catalog\.generated|machines\.ts$/.test(n))).toEqual([])
    expect(readFileSync(join(root, 'agentic-commerce/src/components/launch/launchData.ts'), 'utf8')).toMatch(/showcase\/launch-film/)
  })
})
