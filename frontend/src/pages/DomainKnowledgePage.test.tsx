// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const prov = {
  kind: 'verified_source' as const,
  reference: 'graph/schema',
  verification: 'verified' as const,
}
vi.mock('../store/session', () => ({
  useSession: () => ({ ready: true, user: { id: 'studio-alice' } }),
}))
vi.mock('../api/domainKnowledge', () => ({
  getDomains: vi.fn(async () => ({
    pack: { id: 'noordveld_machinery', version: '1.0.0', synthetic: true },
    domains: [
      {
        id: 'dom_spare_parts',
        name: 'Spare-parts management',
        description: 'Parts.',
        scope: '',
        parent_id: null,
        depends_on: [],
        keywords: [],
        provenance: prov,
        entity_count: 2,
        process_ids: [],
        children: [],
      },
    ],
    decisions: [
      {
        id: 'dec_order_approval',
        question: 'Does any order need approval?',
        status: 'open',
        answer: '',
        affects: [],
        provenance: prov,
      },
    ],
    analysis: {
      findings: [],
      counts: { warning: 0 },
      provenance: { verified_source: 10, synthetic: 5 },
    },
  })),
  getEntities: vi.fn(async () => [
    {
      id: 'part',
      canonical_name: 'Part',
      domain_id: 'dom_spare_parts',
      description: 'A part',
      attribute_count: 1,
      provenance: prov,
      operational_label: 'Part',
    },
    {
      id: 'machine',
      canonical_name: 'Machine',
      domain_id: 'dom_spare_parts',
      description: 'A machine',
      attribute_count: 1,
      provenance: prov,
      operational_label: 'Machine',
    },
  ]),
  getEntity: vi.fn(async (id: string) => ({
    entity: {
      id,
      canonical_name: id === 'part' ? 'Part' : 'Machine',
      domain_id: 'dom_spare_parts',
      description: `The ${id}.`,
      attribute_count: 1,
      provenance: prov,
      operational_label: id === 'part' ? 'Part' : 'Machine',
      natural_keys: [`${id}_id`],
      attributes: [
        {
          id: `${id}_id`,
          name: 'Id',
          type: 'string',
          required: true,
          key: true,
          value_source: 'imported',
          mutability: 'immutable',
          sensitivity: 'internal',
          code_list_id: null,
          provenance: null,
        },
      ],
    },
    concept: {
      id: `concept_${id}`,
      canonical_name: id,
      definition: '',
      synonyms: id === 'part' ? [{ term: 'spare part', domain_id: 'dom_spare_parts' }] : [],
      acronyms: [],
    },
    outgoing:
      id === 'part'
        ? [
            {
              id: 'rel_fits',
              source_id: 'part',
              type: 'FITS',
              target_id: 'machine',
              cardinality: 'many_to_many',
              meaning: 'Fits the model.',
              required: false,
              provenance: prov,
            },
          ]
        : [],
    incoming:
      id === 'machine'
        ? [
            {
              id: 'rel_fits',
              source_id: 'part',
              type: 'FITS',
              target_id: 'machine',
              cardinality: 'many_to_many',
              meaning: 'Fits the model.',
              required: false,
              provenance: prov,
            },
          ]
        : [],
    rules: [],
    processes: [
      { id: 'proc_order', name: 'Spare-parts order', design_template: 'noordveld_spare_parts/wf' },
    ],
    events: [],
    mappings: [],
    decisions: [],
  })),
  getGraph: vi.fn(async () => ({
    nodes: [
      { id: 'part', label: 'Part', domain_id: 'd', provenance: 'verified_source' },
      { id: 'machine', label: 'Machine', domain_id: 'd', provenance: 'verified_source' },
    ],
    edges: [
      {
        id: 'rel_fits',
        source: 'part',
        target: 'machine',
        type: 'FITS',
        cardinality: 'many_to_many',
        provenance: 'verified_source',
      },
    ],
  })),
  getImpact: vi.fn(async () => ({
    item: { id: 'part', group: 'entities', name: 'Part' },
    dependents: [{ id: 'rel_fits', group: 'relationships', name: 'rel_fits' }],
    projects: [],
    project_storage: 'available',
  })),
  searchConcepts: vi.fn(async () => [
    {
      concept_id: 'concept_part',
      entity_id: 'part',
      canonical_name: 'Part',
      domain_id: 'dom_spare_parts',
      kind: 'business_concept',
      matched: ["synonym 'spare part' in dom_spare_parts"],
      provenance: prov,
    },
  ]),
  getPath: vi.fn(async () => ({
    connected: true,
    hops: [
      {
        relationship_id: 'r1',
        type: 'REFERENCES_PART',
        from: 'order_line',
        to: 'part',
        forward: true,
      },
      { relationship_id: 'r2', type: 'FITS', from: 'part', to: 'machine', forward: true },
    ],
  })),
  getPacks: vi.fn(async () => ({
    writable: true,
    active: [{ id: 'noordveld_machinery', version: '1.0.0' }],
    versions: [
      {
        pack_id: 'noordveld_machinery',
        version: '1.0.0',
        status: 'approved',
        content_sha256: 'a',
        proposed_by: 'repository',
        reason: 'Shipped',
        created_at: '',
        title: 'x',
      },
      {
        pack_id: 'noordveld_machinery',
        version: '1.1.0',
        status: 'under_review',
        content_sha256: 'b',
        proposed_by: 'studio-alice',
        reason: 'Add concept',
        created_at: '',
        title: 'x',
      },
    ],
  })),
  comparePack: vi.fn(),
  getGraphStatus: vi.fn(async () => ({
    mode: 'disabled',
    writes_enabled: false,
    isolation: {
      operational_graph_configured: true,
      dedicated_domain_graph_configured: false,
      writes_allowed: false,
      blocker: 'No separate development or domain graph instance is configured.',
    },
    collisions_with_operational_graph: [],
    schema_proposal: ['CREATE CONSTRAINT dk'],
    read_queries: ['entities_in_domain'],
    namespace: { labels: ['DKEntity'], relationship_types: ['DK_RELATES_TO'] },
    write_plan: { statements: 12, rows: 900, executed: false },
    note: 'Not populated.',
  })),
  importDryRun: vi.fn(async () => ({
    valid: true,
    errors: [],
    normalizations: [{ row: 2, column: 'type', original: ' stocks ', normalized: 'STOCKS' }],
    pack_id: 'noordveld_machinery',
    version: '1.2.0',
    content_sha256: 'f'.repeat(64),
    base_version: '1.0.0',
    summary: { added: 1, changed: 0, removed: 0 },
    compatibility: {
      level: 'additive',
      ok: true,
      message: 'additive change from 1.0.0',
      breaking: [],
    },
    analysis: { findings: [], counts: { warning: 0 }, provenance: {} },
    already_present: false,
    version_conflict: false,
  })),
  importApply: vi.fn(async () => ({ proposal: {} })),
  transitionVersion: vi.fn(async () => ({})),
  getDomainPermissions: vi.fn(async () => ({
    user_id: 'studio-alice',
    permissions: ['domain.propose', 'domain.review'],
    store_writable: true,
  })),
  getProposalImpact: vi.fn(async () => ({
    pack_id: 'noordveld_machinery',
    version: '1.1.0',
    base_version: '1.0.0',
    changes: [{ group: 'entities', item_id: 'order', change: 'changed', fields: ['description'] }],
    compatibility: { level: 'patch', message: 'patch change from 1.0.0', ok: true },
    projects: [
      {
        project_id: 'app_x',
        revision: 3,
        entities: ['dk_order'],
        adopted_versions: ['1.0.0'],
        applied: false,
      },
    ],
    project_storage: 'available',
    note: 'Projects keep the definitions they adopted.',
  })),
  traverse: vi.fn(async () => ({
    start: { id: 'order', kind: 'entity', label: 'Order' },
    truncated: false,
    max_depth: 2,
    max_results: 50,
    nodes_expanded: 4,
    results: [
      {
        node: { id: 'role:role_order_processor', kind: 'role', label: 'role_order_processor' },
        depth: 2,
        explanation: 'x',
        hops: [
          {
            from: 'proc',
            to: 'order',
            type: 'USES',
            forward: false,
            explanation: 'Spare-parts order reads or writes order',
          },
          {
            from: 'role',
            to: 'proc',
            type: 'PERFORMS',
            forward: false,
            explanation: 'role role_order_processor performs steps of Spare-parts order',
          },
        ],
      },
    ],
  })),
  exportPackUrl: (id: string, version: string) =>
    `/api/v1/domain-knowledge/packs/${id}/versions/${version}/export`,
}))
import {
  getImpact,
  getProposalImpact,
  importApply,
  importDryRun,
  transitionVersion,
} from '../api/domainKnowledge'
import DomainKnowledgePage from './DomainKnowledgePage'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})
const page = () =>
  render(
    <MemoryRouter>
      <DomainKnowledgePage />
    </MemoryRouter>,
  )

it('explores an entity through the graph and the accessible relationship tables, with provenance and impact', async () => {
  page()
  expect(await screen.findByText(/mostly synthetic demo data/)).toBeTruthy()
  expect(screen.getByText('Does any order need approval?')).toBeTruthy()
  fireEvent.click(await screen.findByRole('button', { name: 'Part' }))
  const panel = await screen.findByRole('article', { name: 'Entity Part' })
  expect(within(panel).getByRole('img', { name: /Relationships around part/ })).toBeTruthy()
  const outgoing = within(panel).getByRole('table', { name: 'Outgoing relationships' })
  expect(within(outgoing).getByText('FITS')).toBeTruthy()
  expect(within(panel).getAllByText('Verified source').length).toBeGreaterThan(0)
  expect(within(panel).getByText(/spare part \(in dom_spare_parts\)/)).toBeTruthy()
  fireEvent.click(within(panel).getByRole('button', { name: 'Analyse impact of a change' }))
  expect(await screen.findByText(/None of your projects use it/)).toBeTruthy()
  expect(getImpact).toHaveBeenCalledWith('part')
  // Navigate along a relationship: the related entity opens.
  fireEvent.click(within(outgoing).getByRole('button', { name: 'machine' }))
  expect(await screen.findByRole('article', { name: 'Entity Machine' })).toBeTruthy()
  fireEvent.keyDown(screen.getByRole('button', { name: 'Open Part' }), { key: 'Enter' })
  expect(await screen.findByRole('article', { name: 'Entity Part' })).toBeTruthy()
})

it('requires a dry run, a reason and another approver; the proposer cannot approve their own version', async () => {
  page()
  fireEvent.click(screen.getByRole('tab', { name: 'Import and versions' }))
  const approve = await screen.findByRole('button', { name: 'Approve' })
  expect((approve as HTMLButtonElement).disabled).toBe(true)
  expect(
    await screen.findByText(/Your domain permissions \(checked by the server\): propose, review/),
  ).toBeTruthy()
  expect((screen.getByRole('button', { name: 'Deprecate' }) as HTMLButtonElement).disabled).toBe(
    true,
  )
  fireEvent.click(screen.getAllByRole('button', { name: 'Impact' })[0])
  expect(await screen.findByText(/app_x r3: dk_order \(adopted 1.0.0\) · not applied/)).toBeTruthy()
  expect(getProposalImpact).toHaveBeenCalledWith('noordveld_machinery', '1.1.0')
  fireEvent.click(screen.getByRole('button', { name: 'Return to draft' }))
  await waitFor(() =>
    expect(transitionVersion).toHaveBeenCalledWith(
      'noordveld_machinery',
      '1.1.0',
      'draft',
      'Returned for changes',
    ),
  )
  fireEvent.change(screen.getByLabelText('Content'), { target: { value: '{"id":"x"}' } })
  expect(screen.queryByRole('button', { name: 'Propose this version for review' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Check import (dry run)' }))
  expect(await screen.findByText(/1 added, 0 changed, 0 removed since 1.0.0/)).toBeTruthy()
  const propose = screen.getByRole('button', {
    name: 'Propose this version for review',
  }) as HTMLButtonElement
  expect(propose.disabled).toBe(true)
  fireEvent.change(screen.getByLabelText('Reason for the change'), {
    target: { value: 'Add a relationship' },
  })
  fireEvent.click(propose)
  await waitFor(() =>
    expect(importApply).toHaveBeenCalledWith(
      { format: 'json', content: '{"id":"x"}' },
      'f'.repeat(64),
      'Add a relationship',
    ),
  )
  expect(importDryRun).toHaveBeenCalledTimes(1)
  // Editing the content discards the reviewed dry run.
  fireEvent.change(screen.getByLabelText('Content'), { target: { value: '{"id":"y"}' } })
  expect(screen.queryByRole('region', { name: 'Dry-run report' })).toBeNull()
})
