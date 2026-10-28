// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type PartOverview, type QueryResponse, type ResultItem } from '../../api/index'
import { errorMessage } from './Notices'

import { ResultCard } from './ResultCard'
import { AvailabilityTable } from './AvailabilityTable'
import { ResultView } from './ResultView'

import { ActionTab } from './tabs/InsightTabs'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const item = (over: Partial<ResultItem> = {}): ResultItem => ({
  kind: 'part',
  key: 'k1',
  title: 'KEY-1',
  subtitle: 'A name',
  part_number: 'KEY-1',
  relationship: 'FITS',
  data_class: 'SOURCE_DERIVED',
  facts: [
    { label: 'Category', value: 'Cat' },
    { label: 'Condition', value: null },
  ],
  groups: [{ label: 'Compatible machines', values: ['M-1', 'M-2'] }],
  ...over,
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
})

describe('errors', () => {
  it('names the language model as the problem when it is unavailable, never the database', () => {
    expect(errorMessage(new ApiError(503, 'llm_unavailable', 'x'))).toMatch(
      /question-understanding service is not available/,
    )
    expect(errorMessage(new ApiError(502, 'llm_invalid_response', 'x'))).toMatch(/rephrase/)
    expect(errorMessage(new ApiError(503, 'graph_unavailable', 'x'))).toMatch(/Neo4j/)
    expect(errorMessage(new ApiError(500, 'error', 'x'))).toMatch(/Check that the API is running/)
  })
})

describe('part workspace', () => {
  const overview = (over: Partial<PartOverview>): PartOverview => ({
    part_id: 'P',
    part_number: 'KEY-1',
    name: 'n',
    description: null,
    category: null,
    subcategory: null,
    families: ['F series'],
    manufacturer: null,
    origin_plant: null,
    status: { code: 'VERIFIED', label: 'Verified', reason: null, data_class: 'SYNTHETIC_DEMO' },
    identification: [],
    data_class: 'SOURCE_DERIVED',
    source: null,
    last_updated: null,
    orderable: true,
    actions: [],
    ...over,
  })

  const action = (
    kind: 'parts_store' | 'identify' | 'request_identification',
    label: string,
    href: string | null = null,
  ) => [{ kind, label, href, question: null }]
  const inRouter = (node: React.ReactNode) => render(<MemoryRouter>{node}</MemoryRouter>)

  beforeEach(() => localStorage.clear())

  it('verified: the action hands the real part number to the Parts Portal', () => {
    const o = overview({
      actions: action('parts_store', 'View in Parts Portal', '/parts-store/KEY-1'),
    })
    inRouter(<ActionTab overview={o} onOpenFitment={() => {}} />)
    expect(screen.getByRole('link', { name: 'View in Parts Portal' }).getAttribute('href')).toBe(
      '/parts-store/KEY-1',
    )
  })
})

describe('answers and recent questions (QA fixes 5 and 6)', () => {
  const response = (demo: boolean): QueryResponse => ({
    question: 'q',
    intent: 'PART_TO_SUPPLIER',
    intent_label: 'Part suppliers',
    understood_by: 'llm',
    entities: [],
    answer: { summary: 'Acme (demo) is connected.', grounded: true, source: 'template', demo },
    results: [],
    total: 0,
    evidence: [
      {
        entity: 'P',
        entity_kind: 'PART',
        relationship: 'SUPPLIED_BY',
        target: 'Acme (demo)',
        target_kind: 'SUPPLIER',
        data_class: 'SYNTHETIC_DEMO',
      },
    ],
    provenance: [],
    graph_path: ['Part', 'SUPPLIED_BY', 'Supplier'],
    warnings: [],
    actions: [],
    clarification: null,
    scope: 'IN_SCOPE',
    stages: [
      { name: 'understanding', ms: 900 },
      { name: 'entities', ms: 40 },
      { name: 'graph', ms: 120 },
      { name: 'answer', ms: 700 },
    ],
    elapsed_ms: 1,
  })
  const view = (demo: boolean) =>
    render(
      <MemoryRouter>
        <ResultView
          response={response(demo)}
          suggestions={null}
          limit={12}
          maxLimit={36}
          onInvestigate={() => {}}
          onAsk={() => {}}
          onSelect={() => {}}
          onMore={() => {}}
        />
      </MemoryRouter>,
    )

  it('shows a visible Demo data notice when the answer includes synthetic data', () => {
    view(true)
    expect(screen.getByRole('note').textContent).toMatch(/^Demo data\./)
    cleanup()
    view(false)
    expect(screen.queryByText(/Demo data\./)).toBeNull()
    cleanup()
    render(
      <AvailabilityTable
        items={[
          item({
            kind: 'dealer',
            title: 'Recorded dealer',
            data_class: 'SYNTHETIC_DEMO',
            facts: [
              { label: 'Available', value: '0' },
              { label: 'Location', value: null },
            ],
          }),
          item({
            key: 'k2',
            kind: 'warehouse',
            title: 'Recorded warehouse',
            facts: [{ label: 'Available', value: '8' }],
          }),
        ]}
      />,
    )
    expect(screen.getByRole('columnheader', { name: 'Available' })).toBeTruthy()
    expect(screen.getByRole('cell', { name: '0' })).toBeTruthy()
    expect(screen.getByRole('cell', { name: '8' })).toBeTruthy()
    expect(screen.getAllByRole('cell', { name: 'Not available' })).toHaveLength(2)
    expect(screen.getByText('Synthetic demo')).toBeTruthy()
  })
})

/** Hard-code audit: Parts Intelligence source holds no catalogue data; real results come only from the API. */
describe('parts intelligence source holds no catalogue data', () => {
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((n) =>
      statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)],
    )
  const src = join(__dirname, '..', '..')
  const files = [
    ...walk(__dirname),
    ...walk(join(src, 'api')).filter((f) => /intelligence/i.test(f)),
    join(src, 'pages/SparkPage.tsx'),
  ].filter((f) => /\.(ts|tsx|css)$/.test(f) && !/\.test\./.test(f))
  const forbidden =
    /NVM-\d{4}|PRT-\d{3}|\b(NV|KFT|BTS)-\d{3,4}\b|\(demo\)|Hanselmann|Drenthe|Nordwest|Radiator assembly|\bSUP-\d|\bDLR-\d|\bWH-\d|€\s?\d|\bEUR\b/

  it('no intelligence source file holds catalogue data', () => {
    expect(files.filter((f) => forbidden.test(readFileSync(f, 'utf8')))).toEqual([])
  })
})
