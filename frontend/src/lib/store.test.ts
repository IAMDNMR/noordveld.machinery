import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getPart, searchParts, type PartQuery } from '../api'
import { partImageUrl } from './assets'
import { availabilityTone, formatMoney, humanize } from './format'
import { categoryPath, PAGE_SIZE, parseQuery, partPath, toParams } from './storeQuery'

const base: PartQuery = { q: '', category: '', machine: '', availability: [], orderable: false, sort: 'relevance', offset: 0, limit: PAGE_SIZE }

describe('store query <-> URL', () => {
  it('round-trips every filter', () => {
    const { page, ...query } = { q: 'pump', category: 'Cooling', machine: 'NV-4500', availability: ['IN_STOCK', 'LIMITED'], orderable: true, sort: 'price_asc' as const, page: 3 }
    const parsed = parseQuery(toParams({ ...query, page }))
    expect(parsed).toMatchObject({ ...query, offset: 2 * PAGE_SIZE, limit: PAGE_SIZE })
  })
  it('omits defaults and ignores junk', () => {
    expect(toParams(base).toString()).toBe('')
    const parsed = parseQuery(new URLSearchParams('sort=bogus&page=-4'))
    expect(parsed.sort).toBe('relevance')
    expect(parsed.offset).toBe(0)
  })
  it('builds browse links', () => {
    expect(partPath('A B/1')).toBe('/parts-store/A%20B%2F1')
    expect(categoryPath('Cab & Controls')).toBe('/parts-store?category=Cab+%26+Controls')
  })
})

describe('formatting', () => {
  it('humanizes API enumerations', () => expect(humanize('IN_STOCK')).toBe('In stock'))
  it('formats money in its own currency', () => expect(formatMoney({ amount: 1234.5, currency: 'EUR' })).toContain('1,234.50'))
  it('gives only IN_STOCK a quiet tone', () => {
    expect(availabilityTone('IN_STOCK')).toBe('ok')
    expect(availabilityTone('LIMITED')).toBe('warn')
    expect(availabilityTone('BACKORDER')).toBe('late')
  })
})

describe('part image resolver', () => {
  it('finds a photo by part number, case-insensitively', () => expect(partImageUrl('NVM-1010-HY')).toBeTruthy())
  it('returns undefined when there is none, so the placeholder renders', () => expect(partImageUrl('NVM-0000-XX')).toBeUndefined())
})

describe('api client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends filters as query parameters and omits empty ones', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, offset: 0, limit: 24 })))
    vi.stubGlobal('fetch', fetchMock)
    await searchParts({ ...base, q: ' pump ', availability: ['IN_STOCK', 'LIMITED'], orderable: true })
    const url = new URL(fetchMock.mock.calls[0][0], 'http://x')
    expect(url.pathname).toBe('/api/v1/parts')
    expect(url.searchParams.get('q')).toBe('pump')
    expect(url.searchParams.getAll('availability')).toEqual(['IN_STOCK', 'LIMITED'])
    expect(url.searchParams.has('category')).toBe(false)
  })
  it('maps structured API errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'not_found', message: 'nope' } }), { status: 404 })))
    const error = await getPart('X').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, code: 'not_found', notFound: true })
  })
  it('reports an unreachable service', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')))
    await expect(getPart('X')).rejects.toMatchObject({ status: 0, code: 'network' })
  })
})

/** Hard-code audit: the catalogue lives in the graph. No store source file may contain part numbers, part ids or machine models. */
describe('frontend holds no catalogue data', () => {
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name)
      return statSync(path).isDirectory() ? walk(path) : [path]
    })
  const root = join(__dirname, '..')
  const storeFiles = [...walk(join(root, 'api')), ...walk(join(root, 'components/store')), join(root, 'pages/PartsStorePage.tsx'), join(root, 'pages/PartDetailPage.tsx'), join(root, 'pages/CheckoutPage.tsx'), join(root, 'store/CartContext.tsx'), ...walk(join(root, 'lib')).filter((f) => !f.endsWith('.test.ts'))]
  const forbidden = /NVM-\d{4}|PRT-\d{3}|\b(NV|KFT|BTS)-\d{3,4}\b/

  it.each(storeFiles.filter((f) => /\.(ts|tsx)$/.test(f)))('%s', (file) => {
    expect(readFileSync(file, 'utf8')).not.toMatch(forbidden)
  })
})
