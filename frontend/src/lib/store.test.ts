import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getPart,   } from '../api/index'

import {  formatMoney,  } from './format'
import {  PAGE_SIZE, parseQuery,  toParams } from './storeQuery'



describe('store query <-> URL', () => {
  it('round-trips every filter', () => {
    const { page, ...query } = {
      q: 'pump',
      category: 'Cooling',
      machine: 'NV-4500',
      availability: ['IN_STOCK', 'LIMITED'],
      orderable: true,
      sort: 'price_asc' as const,
      page: 3,
    }
    const parsed = parseQuery(toParams({ ...query, page }))
    expect(parsed).toMatchObject({ ...query, offset: 2 * PAGE_SIZE, limit: PAGE_SIZE })
  })
  
  
})

describe('formatting', () => {
  
  it('formats money in its own currency', () =>
    expect(formatMoney({ amount: 1234.5, currency: 'EUR' })).toContain('1,234.50'))
  
})



describe('api client', () => {
  afterEach(() => vi.unstubAllGlobals())

  
  it('maps structured API errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: 'not_found', message: 'nope' } }), {
          status: 404,
        }),
      ),
    )
    const error = await getPart('X').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, code: 'not_found', notFound: true })
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
  const storeFiles = [
    ...walk(join(root, 'api')),
    ...walk(join(root, 'components/store')),
    join(root, 'pages/PartsStorePage.tsx'),
    join(root, 'pages/PartDetailPage.tsx'),
    join(root, 'pages/CheckoutPage.tsx'),
    join(root, 'store/CartContext.tsx'),
    ...walk(join(root, 'lib')).filter((f) => !f.endsWith('.test.ts')),
  ]
  const forbidden = /NVM-\d{4}|PRT-\d{3}|\b(NV|KFT|BTS)-\d{3,4}\b/

  it('no store source file holds catalogue data', () => {
    const offenders = storeFiles
      .filter((f) => /\.(ts|tsx)$/.test(f))
      .filter((f) => forbidden.test(readFileSync(f, 'utf8')))
    expect(offenders).toEqual([])
  })
})
