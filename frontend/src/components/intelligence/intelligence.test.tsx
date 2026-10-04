// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, askQuestion, type DataClass, type PartOverview, type QueryResponse, type ResultItem } from '../../api'
import { ErrorNotice, errorMessage } from './Notices'
import { TABS } from './PartWorkspace'
import { DATA_CLASS_LABEL, ProvenanceBadge } from './provenance'
import { ResultCard } from './ResultCard'
import { ResultView } from './ResultView'
import { labelQuestion, rememberQuestion, whenAsked } from '../../store/recentQuestions'
import { PartActions, StatusBadge } from './PartWorkspace'
import { ActionTab } from './tabs/InsightTabs'

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
  it('names the language model as the problem when it is unavailable, never the database', () => {
    expect(errorMessage(new ApiError(503, 'llm_unavailable', 'x'))).toMatch(/question-understanding service is not available/)
    expect(errorMessage(new ApiError(502, 'llm_invalid_response', 'x'))).toMatch(/rephrase/)
    expect(errorMessage(new ApiError(503, 'graph_unavailable', 'x'))).toMatch(/Neo4j/)
    expect(errorMessage(new ApiError(500, 'error', 'x'))).toMatch(/Check that the API is running/)
  })

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
    part_id: 'P', part_number: 'KEY-1', name: 'n', description: null, category: null, subcategory: null, families: ['F series'], manufacturer: null, origin_plant: null,
    status: { code: 'VERIFIED', label: 'Verified', reason: null, data_class: 'SYNTHETIC_DEMO' }, identification: [], data_class: 'SOURCE_DERIVED', source: null, last_updated: null,
    orderable: true, actions: [], ...over,
  })
  const status = (code: PartOverview['status']['code'], label: string) => ({ code, label, reason: 'Because.', data_class: 'SYNTHETIC_DEMO' as const })
  const action = (kind: 'parts_store' | 'identify' | 'request_identification', label: string, href: string | null = null) => [{ kind, label, href, question: null }]
  const inRouter = (node: React.ReactNode) => render(<MemoryRouter>{node}</MemoryRouter>)

  beforeEach(() => localStorage.clear())

  it('verified: the action hands the real part number to the Parts Store', () => {
    const o = overview({ actions: action('parts_store', 'View in Parts Store', '/parts-store/KEY-1') })
    inRouter(<ActionTab overview={o} onOpenFitment={() => {}} />)
    expect(screen.getByRole('link', { name: 'View in Parts Store' }).getAttribute('href')).toBe('/parts-store/KEY-1')
  })

  it.each([
    ['IDENTIFICATION_REQUIRED', 'Identification required', 'Identify Part'],
    ['AMBIGUOUS', 'Ambiguous', 'Identify machine / variant / serial'],
  ] as const)('%s: no ordering; a form takes the machine and serial, stores it and shows it back without verifying', (code, label, actionLabel) => {
    const o = overview({ status: status(code, label), orderable: false, actions: action('identify', actionLabel), identification: [{ model_code: 'M-1', reason: label, needed: 'Machine variant or serial range' }] })
    inRouter(<><StatusBadge overview={o} /><ActionTab overview={o} onOpenFitment={() => {}} /></>)
    expect(screen.queryByRole('link', { name: /parts store/i })).toBeNull()
    expect(screen.getByRole('heading', { name: actionLabel })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Machine model'), { target: { value: 'M-1' } })
    fireEvent.change(screen.getByLabelText('Serial number or variant'), { target: { value: 'SN-42' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save identification' }))
    expect(screen.getByRole('status').textContent).toMatch(/machine M-1, serial or variant SN-42/)
    expect(screen.getByRole('status').textContent).toMatch(new RegExp(`stays ${label.toLowerCase()}`))
    expect(document.querySelector('.pw__status')?.textContent).toMatch(new RegExp(`^${label}`)) // status unchanged; only 'details submitted' is added
    cleanup()
    inRouter(<ActionTab overview={o} onOpenFitment={() => {}} />) // "reload"
    expect(screen.getByRole('status').textContent).toMatch(/SN-42/)
  })

  it('unverified: request identification is saved, shown as requested and disabled after a reload', () => {
    const o = overview({ status: status('UNVERIFIED', 'Unverified'), orderable: false, actions: action('request_identification', 'Request identification') })
    inRouter(<><StatusBadge overview={o} /><PartActions overview={o} onIdentify={() => {}} /></>)
    fireEvent.click(screen.getByRole('button', { name: 'Request identification' }))
    cleanup()
    inRouter(<><StatusBadge overview={o} /><PartActions overview={o} onIdentify={() => {}} /><ActionTab overview={o} onOpenFitment={() => {}} /></>)
    const button = screen.getByRole('button', { name: 'Identification requested' })
    expect((button as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getAllByText('Identification requested').length).toBeGreaterThanOrEqual(2)
  })

  it('never shows a raw status code', () => {
    for (const [code, label] of [['VERIFIED', 'Verified'], ['IDENTIFICATION_REQUIRED', 'Identification required'], ['AMBIGUOUS', 'Ambiguous'], ['UNVERIFIED', 'Unverified']] as const) {
      const { container } = inRouter(<StatusBadge overview={overview({ status: status(code, label) })} />)
      expect(container.textContent).toBe(label)
      cleanup()
    }
  })
})

describe('answers and recent questions (QA fixes 5 and 6)', () => {
  const response = (demo: boolean): QueryResponse => ({
    question: 'q', intent: 'PART_TO_SUPPLIER', intent_label: 'Part suppliers', understood_by: 'llm', entities: [],
    answer: { summary: 'Acme (demo) is connected.', grounded: true, source: 'template', demo }, results: [], total: 0,
    evidence: [{ entity: 'P', entity_kind: 'PART', relationship: 'SUPPLIED_BY', target: 'Acme (demo)', target_kind: 'SUPPLIER', data_class: 'SYNTHETIC_DEMO' }],
    provenance: [], graph_path: ['Part', 'SUPPLIED_BY', 'Supplier'], warnings: [], actions: [], clarification: null, scope: 'IN_SCOPE',
    stages: [{ name: 'understanding', ms: 900 }, { name: 'entities', ms: 40 }, { name: 'graph', ms: 120 }, { name: 'answer', ms: 700 }], elapsed_ms: 1,
  })
  const view = (demo: boolean) => render(<MemoryRouter><ResultView response={response(demo)} suggestions={null} limit={12} maxLimit={36} onInvestigate={() => {}} onAsk={() => {}} onSelect={() => {}} onMore={() => {}} /></MemoryRouter>)

  it('shows a visible Demo data notice when the answer includes synthetic data', () => {
    view(true)
    expect(screen.getByRole('note').textContent).toMatch(/^Demo data\./)
    cleanup()
    view(false)
    expect(screen.queryByText(/Demo data\./)).toBeNull()
  })

  it('names the part an answer is about before the machines that belong to it', () => {
    const investigated: string[] = []
    const r: QueryResponse = {
      ...response(false), intent: 'PART_TO_MACHINE', intent_label: 'Part to machine',
      subject: { kind: 'PART', key: 'P1', label: 'AB-1', name: 'Bucket, general purpose', facts: [{ label: 'Category', value: 'Attachments' }], data_class: 'SOURCE_DERIVED' },
      answer: { summary: 'AB-1 (Bucket, general purpose) is associated with 2 machines.', grounded: true, source: 'template', demo: false },
      results: [{ kind: 'machine', key: 'M1', title: 'ZZ-1', subtitle: 'ZZ-1 Wheel Loader', part_number: null, relationship: 'FITS', data_class: 'SOURCE_DERIVED', facts: [], groups: [] }], total: 1,
    }
    render(<MemoryRouter><ResultView response={r} suggestions={null} limit={12} maxLimit={36} onInvestigate={(pn) => investigated.push(pn)} onAsk={() => {}} onSelect={() => {}} onMore={() => {}} /></MemoryRouter>)
    const subject = screen.getByLabelText('About part AB-1')
    expect(subject.textContent).toMatch(/PartAB-1Bucket, general purpose.*Source-derived/)
    expect(subject.textContent).toMatch(/CategoryAttachments/)
    fireEvent.click(screen.getByRole('button', { name: 'AB-1' }))
    expect(investigated).toEqual(['AB-1'])
  })

  it('lists evidence rows in "How this was answered"', () => {
    view(true)
    expect(screen.getAllByRole('row').length).toBe(2) // header + one evidence row
  })

  it('says the model understood the question and shows the measured steps, never a prompt', () => {
    const { container } = view(true)
    const text = container.querySelector('.evid')?.textContent ?? ''
    expect(text).toMatch(/understood by the language model/)
    expect(text).toMatch(/Understanding 900 ms · Entities 40 ms · Knowledge graph 120 ms · Answer 700 ms/)
    expect(text).not.toMatch(/prompt|system instruction/i)
  })

  it('keeps a labelled, timestamped history: newest first, no duplicates, capped', () => {
    localStorage.clear()
    const read = () => JSON.parse(localStorage.getItem('noordveld-pi-history-v1') ?? '[]') as { question: string; label?: string }[]
    rememberQuestion('first?')
    rememberQuestion('second?')
    labelQuestion('first?', 'Part suppliers')
    rememberQuestion('FIRST?')
    expect(read().map((q) => q.question)).toEqual(['FIRST?', 'second?'])
    expect(read()[0].label).toBe('Part suppliers') // asking again keeps what it was understood as
    for (let i = 0; i < 30; i++) rememberQuestion(`q${i}`)
    expect(read()).toHaveLength(20)
  })

  it('words when a question was asked', () => {
    const now = new Date(2026, 9, 3, 12, 0)
    expect(whenAsked(new Date(2026, 9, 3, 10, 24).getTime(), now)).toBe('Today, 10:24')
    expect(whenAsked(new Date(2026, 9, 2, 16, 12).getTime(), now)).toBe('Yesterday, 16:12')
    expect(whenAsked(new Date(2026, 8, 28, 9, 5).getTime(), now)).toBe('28 Sep, 09:05')
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
