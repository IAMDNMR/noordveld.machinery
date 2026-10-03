// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, askQuestion, type DataClass, type PartOverview, type ResultItem } from '../../api'
import { ErrorNotice } from './Notices'
import { TABS } from './PartWorkspace'
import { DATA_CLASS_LABEL, ProvenanceBadge } from './provenance'
import { ResultCard } from './ResultCard'
import { StoreTab } from './tabs/InsightTabs'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const item = (over: Partial<ResultItem> = {}): ResultItem => ({
  kind: 'part', key: 'k1', title: 'KEY-1', subtitle: 'A name', part_number: 'KEY-1', relationship: 'FITS', data_class: 'SOURCE_DERIVED',
  facts: [{ label: 'Category', value: 'Cat' }, { label: 'Condition', value: null }], groups: [{ label: 'Compatible machines', values: ['M-1', 'M-2'] }], ...over,
})

describe('result card', () => {
  it('puts the part number first and makes it open the workspace', () => {
    const onInvestigate = vi.fn()
    render(<ResultCard item={item()} onInvestigate={onInvestigate} />)
    expect(screen.getByRole('heading', { level: 3 }).textContent).toBe('KEY-1')
    fireEvent.click(screen.getByRole('button', { name: 'Open KEY-1 in Part Intelligence' }))
    fireEvent.click(screen.getByRole('button', { name: 'View Part Intelligence' }))
    expect(onInvestigate).toHaveBeenCalledTimes(2)
    expect(onInvestigate).toHaveBeenCalledWith('KEY-1')
  })
  it('gives each fact its own label and shows missing values as Not available, never blank or zero', () => {
    render(<ResultCard item={item()} onInvestigate={() => {}} />)
    expect(screen.getAllByRole('term').map((t) => t.textContent)).toEqual(['Category', 'Condition'])
    expect(screen.getByText('Not available')).toBeTruthy()
    expect(screen.getAllByRole('listitem').map((l) => l.textContent)).toEqual(['M-1', 'M-2'])
  })
  it('does not offer an investigate action for things that are not parts', () => {
    render(<ResultCard item={item({ kind: 'supplier', part_number: null })} onInvestigate={() => {}} />)
    expect(screen.queryByRole('button')).toBeNull()
  })
  it('states where the data comes from in words, not only colour', () => {
    render(<ResultCard item={item({ data_class: 'SYNTHETIC_DEMO' })} onInvestigate={() => {}} />)
    expect(screen.getByText(/Synthetic demo/)).toBeTruthy()
  })
})

describe('provenance', () => {
  it('has a readable label for every data class', () => {
    const classes: DataClass[] = ['REAL', 'SOURCE_DERIVED', 'DERIVED', 'SYNTHETIC_DEMO', 'USER_PROVIDED', 'TEST_DATA', 'INTERNAL_REFERENCE_ONLY', 'UNKNOWN', 'NOT_CONNECTED']
    for (const c of classes) {
      render(<ProvenanceBadge value={c} />)
      expect(screen.getByText(new RegExp(DATA_CLASS_LABEL[c]))).toBeTruthy()
      cleanup()
    }
  })
})

describe('errors', () => {
  it.each([
    [new ApiError(503, 'graph_unavailable', 'x'), /Neo4j is currently unavailable/],
    [new ApiError(0, 'network', 'x'), /could not be reached/],
    [new ApiError(422, 'validation', 'x'), /rephrasing/],
  ])('explains %s in plain language', (error, text) => {
    render(<ErrorNotice error={error} />)
    expect(screen.getByRole('alert').textContent).toMatch(text)
  })
})

describe('part workspace', () => {
  it('has the twelve investigation tabs from the brief', () => {
    expect(TABS.map((t) => t.label)).toEqual([
      'Overview', 'Machine & Fitment', 'Related Parts', 'Assembly / Components', 'Supplier Intelligence', 'Dealer / Location', 'Inventory / Availability', 'Compliance',
      'Graph Relationships', 'Data & Provenance', 'Intelligence / Insights', 'Parts Store Action',
    ])
  })

  const overview = (over: Partial<PartOverview>): PartOverview => ({
    part_id: 'P', part_number: 'KEY-1', name: 'n', description: null, category: null, subcategory: null, manufacturer: null, origin_plant: null,
    status: { code: 'VERIFIED', label: 'Verified' }, identification: [], data_class: 'SOURCE_DERIVED', source: null, last_updated: null, orderable: true, actions: [], ...over,
  })

  it('hands a verified, orderable part to the Parts Store using the real part number', () => {
    render(
      <MemoryRouter>
        <StoreTab overview={overview({ actions: [{ kind: 'parts_store', label: 'View in Parts Store', href: '/parts-store/KEY-1', question: null }] })} onIdentify={() => {}} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'View in Parts Store' }).getAttribute('href')).toBe('/parts-store/KEY-1')
  })

  it('never offers ordering for a part that still needs identification, and the next step is actionable', () => {
    const onIdentify = vi.fn()
    render(
      <MemoryRouter>
        <StoreTab overview={overview({ status: { code: 'IDENTIFICATION_REQUIRED', label: 'Identification required' }, orderable: true })} onIdentify={onIdentify} />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('link')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Identify part' }))
    expect(onIdentify).toHaveBeenCalled()
  })

  it('does not offer ordering for an unverified part', () => {
    render(
      <MemoryRouter>
        <StoreTab overview={overview({ status: { code: 'UNVERIFIED', label: 'Unverified' }, orderable: null })} onIdentify={() => {}} />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.getByText(/online ordering is not configured/)).toBeTruthy()
  })
})

describe('question API', () => {
  it('posts the question, the chosen entities and the limit to the backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ intent: 'X' })))
    vi.stubGlobal('fetch', fetchMock)
    await askQuestion('which parts fit it?', [{ kind: 'MACHINE', key: 'M' }], 24)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/intelligence/query')
    expect(JSON.parse(init.body)).toEqual({ question: 'which parts fit it?', selected: [{ kind: 'MACHINE', key: 'M' }], limit: 24 })
  })
})

/** Hard-code audit: Parts Intelligence source holds no catalogue data; real results come only from the API. */
describe('parts intelligence source holds no catalogue data', () => {
  const walk = (dir: string): string[] => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]))
  const src = join(__dirname, '..', '..')
  const files = [
    ...walk(__dirname), ...walk(join(src, 'api')).filter((f) => /intelligence/i.test(f)), join(src, 'pages/PartsIntelligencePage.tsx'),
  ].filter((f) => /\.(ts|tsx|css)$/.test(f) && !/\.test\./.test(f))
  const forbidden = /NVM-\d{4}|PRT-\d{3}|\b(NV|KFT|BTS)-\d{3,4}\b|\(demo\)|Hanselmann|Drenthe|Nordwest|Radiator assembly|\bSUP-\d|\bDLR-\d|\bWH-\d|€\s?\d|\bEUR\b/

  it.each(files)('%s', (file) => {
    expect(readFileSync(file, 'utf8')).not.toMatch(forbidden)
  })
})
