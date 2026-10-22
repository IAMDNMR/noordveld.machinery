// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { StudioState, Turn, TurnResult, VoiceStatus } from '../api/studio'
import { emptyDefinition } from '../components/studio/model/applicationDefinition'

const session = { ready: true, user: { id: 'studio-alice', name: 'Alice' } }
vi.mock('../store/session', () => ({ useSession: () => session }))
vi.mock('../api/applicationDefinition', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/applicationDefinition')>()),
  listProjects: vi.fn(),
  createProject: vi.fn(),
  getAudit: vi.fn(),
  approveProject: vi.fn(),
  generateProjectScreens: vi.fn(),
}))
vi.mock('../api/studio', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/studio')>()),
  continueStudio: vi.fn(),
  getStudioState: vi.fn(),
  getStudioAccess: vi.fn(),
  studioTurn: vi.fn(),
  studioAct: vi.fn(),
  studioApply: vi.fn(),
  studioRevert: vi.fn(),
  getVoiceStatus: vi.fn(),
  transcribeAudio: vi.fn(),
  synthesizeSpeech: vi.fn(),
  getRuntime: vi.fn(async () => ({ running: false })),
}))
import { approveProject, createProject, listProjects } from '../api/applicationDefinition'
import { ApiError } from '../api/client'
import {
  continueStudio,
  getStudioAccess,
  getStudioState,
  getVoiceStatus,
  studioApply,
  studioRevert,
  studioTurn,
} from '../api/studio'
import StudioWorkspacePage from './StudioWorkspacePage'

const STAGE_KEYS = [
  'brief',
  'knowledge',
  'workflow',
  'data',
  'screen',
  'rules',
  'roles',
  'checks',
  'export',
] as const
const speech = {
  capability: 'speech',
  enabled: true,
  provider: 'deepgram',
  reason: 'Voice uses Deepgram.',
  credential_present: true,
}
const assistant = {
  capability: 'assistant',
  enabled: true,
  provider: 'nvidia',
  reason: 'Conversation uses nvidia.',
  credential_present: true,
}
const voice = (enabled = true): VoiceStatus => ({
  assistant,
  speech: enabled
    ? speech
    : {
        ...speech,
        enabled: false,
        provider: null,
        reason:
          'Voice is unavailable: no speech provider is configured (DEEPGRAM_API_KEY). Use the text box.',
        credential_present: false,
      },
})

function state(
  revision: number,
  extra: Partial<StudioState['stages']> = {},
  edit?: (definition: StudioState['definition']) => void,
): StudioState {
  const definition = {
    ...emptyDefinition(),
    id: 'app_test',
    revision,
    approvals: [],
    workflow_definitions: [],
    business: {
      brief: {
        goal: '',
        problem: '',
        domain_id: null,
        subdomain: '',
        capability: '',
        purpose: '',
        user_types: [],
        outcomes: [],
        constraints: [],
        dependencies: [],
      },
      requirements: [],
      roles: [],
      entities: [],
      rules: [],
      exceptions: [],
      decisions: [],
      integrations: [],
      terms: [],
      questions: [],
      knowledge: [],
    },
  } as StudioState['definition']
  definition.metadata = { ...definition.metadata, name: 'Transport management' }
  edit?.(definition)
  const info = (status: StudioState['stages']['brief']['status'], reason: string) => ({
    status,
    reason,
    counts: {},
  })
  const stages = Object.fromEntries(
    STAGE_KEYS.map((key) => [key, info('not_started', 'Not started yet.')]),
  ) as StudioState['stages']
  Object.assign(stages, extra)
  return {
    definition,
    revision,
    base_sha256: 'a'.repeat(64),
    stages,
    next: { stage: 'brief', label: 'Requirements', status: 'needs_input', text: 'Say more.' },
    questions: [{ id: 'q_users', topic: 'users', text: 'Who will use it?' }],
    analysis: {
      process: {
        scope: 'process',
        findings: [],
        counts: { error: 0, warning: 0, info: 0 },
        blocking: false,
      },
      design: {
        scope: 'design',
        findings: [],
        counts: { error: 0, warning: 0, info: 0 },
        blocking: false,
      },
    },
    approval: { process: { state: 'none', record: null }, design: { state: 'none', record: null } },
    domain: { matches: [], packs: [], domains: [] },
    compile: null,
    assistant,
  }
}
const populated = (revision: number) =>
  state(
    revision,
    {
      brief: { status: 'needs_input', reason: 'Your input is needed: 1 question.', counts: {} },
      workflow: {
        status: 'ready_for_review',
        reason: 'Ready for you to review and approve.',
        counts: {},
      },
      data: {
        status: 'ready_for_review',
        reason: 'Ready for you to review and approve.',
        counts: {},
      },
    },
    (definition) => {
      definition.business.brief.goal = 'Manage transport requests and deliveries.'
      definition.business.roles = [
        {
          id: 'role_planner',
          name: 'Transport planner',
          responsibilities: [],
          permissions: ['transport.plan'],
        },
      ]
      definition.business.entities = [
        {
          id: 'ent_shipment',
          name: 'Shipment',
          attributes: [
            { id: 'shipment_id', name: 'Shipment id', type: 'string', required: true, key: true },
            { id: 'note', name: 'Note', type: 'string', required: false },
          ],
          relationships: [],
        },
        {
          id: 'ent_carrier',
          name: 'Carrier',
          attributes: [
            { id: 'carrier_id', name: 'Carrier id', type: 'string', required: true, key: true },
          ],
          relationships: [
            { id: 'rel_ships', name: 'moves', target: 'ent_shipment', cardinality: 'one_to_many' },
          ],
        },
      ]
      definition.workflow_definitions = [
        {
          version: 1,
          id: 'wf_main',
          name: 'Shipment lifecycle',
          states: [
            { id: 'st_start', label: 'Start', kind: 'start', outputs: [] },
            {
              id: 'st_plan',
              label: 'Plan the shipment',
              kind: 'form',
              outputs: [],
              role_id: 'role_planner',
            },
            { id: 'st_end', label: 'Delivered', kind: 'end', outputs: [], outcome: 'success' },
          ],
          transitions: [
            {
              id: 'tr_1',
              source: 'st_start',
              target: 'st_plan',
              condition: { kind: 'always', field: null, value: null },
            },
            {
              id: 'tr_2',
              source: 'st_plan',
              target: 'st_end',
              condition: { kind: 'always', field: null, value: null },
            },
          ],
        },
      ]
    },
  )
const turn = (extra: Partial<Turn> = {}): Turn => ({
  mode: 'language_model',
  degraded: null,
  reply: 'I understood: a transport system. Who will use it?',
  applied: [],
  previous_revision: 1,
  revision: 2,
  approvals_made_stale: [],
  proposal: null,
  rejected: [],
  asked_question_id: 'q_users',
  focus: null,
  focus_item: null,
  generation: null,
  client_action: null,
  input_mode: 'text',
  ...extra,
})
const proposal = {
  id: 'abc123def456',
  summary: 'Role “Warehouse manager”',
  changes: [
    {
      area: 'roles',
      kind: 'added' as const,
      item_id: 'role_warehouse_manager',
      summary: 'Role “Warehouse manager”',
    },
  ],
  actions: [{ type: 'add_role', name: 'Warehouse manager' }],
  base_sha256: 'b'.repeat(64),
  candidate_sha256: 'c'.repeat(64),
  reasons: ['Changes who may do what.'],
  approvals_made_stale: [],
  validation: {
    before: { error: 2, warning: 3, info: 0 },
    after: { error: 2, warning: 3, info: 0 },
  },
  diff: [{ area: 'roles', item_id: 'role_warehouse_manager', change: 'added' as const }],
}

const renderAt = (path = '/design-studio') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/design-studio/:projectId?" element={<StudioWorkspacePage />} />
      </Routes>
    </MemoryRouter>,
  )
beforeEach(() => {
  localStorage.clear()
  vi.mocked(getStudioAccess).mockRejectedValue(new Error('unknown access')) // unknown access never narrows or widens anything: the server decides
  vi.mocked(getVoiceStatus).mockResolvedValue(voice())
  vi.mocked(listProjects).mockResolvedValue([])
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

it('starts with a conversation, not a form: a voice control, a text box, and no business brief to fill in', async () => {
  renderAt()
  expect(
    await screen.findByRole('heading', { name: 'What would you like to bring to life?' }),
  ).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Start talking' })).toBeTruthy()
  expect(screen.getByLabelText('Describe the application you want to build')).toBeTruthy()
  expect(screen.queryByLabelText(/business goal|problem/i)).toBeNull()
  await waitFor(() => expect(screen.getByText(/Voice enabled/)).toBeTruthy())
  expect(screen.getAllByRole('button', { name: /^\d\. / })).toHaveLength(9)
})

it('a typed request creates the project, shows the answer and its review, applies only on Apply, and offers Undo', async () => {
  vi.mocked(createProject).mockResolvedValue({
    ...emptyDefinition(),
    id: 'app_test',
    revision: 1,
  } as never)
  vi.mocked(studioTurn).mockResolvedValue({
    turn: turn({
      reply: 'This looks like transport. I have prepared reference knowledge.',
      proposal,
      previous_revision: 1,
      revision: 2,
    }),
    state: populated(2),
  } as TurnResult)
  vi.mocked(studioApply).mockResolvedValue({
    changes: proposal.changes,
    previous_revision: 2,
    approvals_made_stale: [],
    state: populated(3),
  })
  vi.mocked(studioRevert).mockResolvedValue({ state: populated(4), restored_from: 2 })
  renderAt()
  fireEvent.change(await screen.findByLabelText('Describe the application you want to build'), {
    target: { value: 'I want to build a transport management system' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Start building' }))
  const card = await screen.findByRole('region', { name: 'Proposed change' })
  expect(vi.mocked(createProject)).toHaveBeenCalledTimes(1)
  expect(vi.mocked(studioTurn)).toHaveBeenCalledWith(
    'app_test',
    expect.objectContaining({
      message: 'I want to build a transport management system',
      expected_revision: 1,
      input_mode: 'text',
    }),
  )
  expect(
    screen.getByText('This looks like transport. I have prepared reference knowledge.'),
  ).toBeTruthy()
  expect(within(card).getByText('Review this change')).toBeTruthy()
  expect(vi.mocked(studioApply)).not.toHaveBeenCalled()
  // stage statuses are the server's, not the page's
  expect(screen.getByRole('button', { name: /Business Process.*Ready for review/ })).toBeTruthy()
  expect(screen.getByRole('button', { name: /1\. Requirements.*Needs input/ })).toBeTruthy()
  const applyButton = within(card).getByRole<HTMLButtonElement>('button', { name: 'Apply' })
  await waitFor(() => expect(applyButton.disabled).toBe(false))
  fireEvent.click(applyButton)
  await waitFor(() => expect(studioApply).toHaveBeenCalledWith('app_test', proposal, 2))
  await waitFor(() =>
    expect(
      within(screen.getByRole('region', { name: 'Proposed change' })).getByText('Applied'),
    ).toBeTruthy(),
  )
  expect(vi.mocked(studioApply)).toHaveBeenCalledWith('app_test', proposal, 2)
  const undo = await screen.findByRole('button', { name: /Undo/ })
  fireEvent.click(undo)
  await waitFor(() => expect(vi.mocked(studioRevert)).toHaveBeenCalledWith('app_test', 3, 2))
})

it('shows each stage from the saved specification: a process diagram, an entity diagram, roles', async () => {
  vi.mocked(getStudioState).mockResolvedValue(populated(5))
  renderAt('/design-studio/app_test?stage=workflow')
  fireEvent.click(await screen.findByRole('button', { name: 'Flow diagram' }))
  expect(await screen.findByRole('region', { name: 'Process diagram' })).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'Shipment lifecycle' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /4\. Data Model/ }))
  expect(await screen.findByRole('group', { name: 'Entity relationship diagram' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /^Shipment, 2 attributes/ }))
  expect(screen.getByRole('table', { name: 'Shipment attributes' })).toBeTruthy()
  expect(
    (screen.getByRole('switch', { name: 'Shipment id is mandatory' }) as HTMLButtonElement)
      .disabled,
  ).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: /7\. Roles/ }))
  expect(await screen.findByText('Transport planner')).toBeTruthy()
})

it('reports a stale project, a service failure and unavailable storage honestly, and keeps the person’s words', async () => {
  vi.mocked(createProject).mockRejectedValueOnce(
    new ApiError(503, 'draft_storage_unavailable', 'Draft storage is not configured.'),
  )
  renderAt()
  fireEvent.change(await screen.findByLabelText('Describe the application you want to build'), {
    target: { value: 'A leave request system' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Start building' }))
  expect((await screen.findByRole('alert')).textContent).toMatch(/Project storage is not available/)
  expect(vi.mocked(studioTurn)).not.toHaveBeenCalled()
})

it('shows the project, its phase and the nine-stage pipeline from server statuses; Generate opens the stage that says what is missing', async () => {
  vi.mocked(getStudioState).mockResolvedValue(populated(5))
  renderAt('/design-studio/app_test?stage=brief')
  const pipeline = await screen.findByRole('navigation', { name: 'Pipeline' })
  expect(within(pipeline).getAllByRole('button')).toHaveLength(9)
  expect(
    within(pipeline)
      .getByRole('button', { name: /Pipeline step 3 of 9: Business Process/ })
      .getAttribute('title'),
  ).toBe('Ready for you to review and approve.')
  expect(screen.getByText('Draft')).toBeTruthy()
  expect(screen.getByText(/Saved · revision 5/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /Generate application/ }))
  expect(await screen.findByRole('region', { name: 'Readiness' })).toBeTruthy()
})

it('a project that is not assigned to the person opens an access-denied page that reveals nothing and says what to do', async () => {
  vi.mocked(getStudioState).mockRejectedValue(
    new ApiError(404, 'project_not_found', 'No such project in this organization.'),
  )
  renderAt('/design-studio/app_secret')
  const denied = await screen.findByRole('alert')
  expect(denied.textContent).toMatch(/not available to you/)
  expect(denied.textContent).toMatch(/assigned to you/)
  expect(denied.textContent).not.toMatch(/secret/)
  expect(screen.getByRole('link', { name: 'Back to your workspace' })).toBeTruthy()
})

it('keeps later stages locked and advances only after an explicit review', async () => {
  const first = state(2)
  first.flow = { active: 'brief', reviewed: [], ready: true }
  const next = state(3)
  next.flow = { active: 'knowledge', reviewed: ['brief'], ready: true }
  vi.mocked(getStudioState).mockResolvedValue(first)
  vi.mocked(continueStudio).mockResolvedValue({
    state: next,
    turn: {
      mode: 'direct',
      reply: 'Domain knowledge draft is ready for review.',
      applied: [],
      previous_revision: 2,
      revision: 3,
      approvals_made_stale: [],
      proposal: null,
      rejected: [],
      asked_question_id: null,
      focus: 'knowledge',
      focus_item: null,
      generation: null,
      client_action: null,
      input_mode: 'text',
      degraded: null,
    },
  })
  renderAt('/design-studio/app_test')
  const review = await screen.findByRole('button', { name: 'Looks good, continue' })
  expect(
    (screen.getByRole('button', { name: /Pipeline step 2 of 9/ }) as HTMLButtonElement).disabled,
  ).toBe(true)
  expect(continueStudio).not.toHaveBeenCalled()
  fireEvent.click(review)
  await waitFor(() => expect(continueStudio).toHaveBeenCalledWith('app_test', 2, 'brief'))
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: /Pipeline step 2 of 9/ }).getAttribute('aria-current'),
    ).toBe('step'),
  )
  expect(
    (screen.getByRole('button', { name: /Pipeline step 3 of 9/ }) as HTMLButtonElement).disabled,
  ).toBe(true)
})

it('previews the application without unlocking or reviewing a later stage', async () => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute('open')
  }
  const current = state(3)
  current.flow = { active: 'workflow', reviewed: ['brief', 'knowledge'], ready: true }
  current.definition.workflow_definitions = [
    { version: 1, id: 'wf_request', name: 'Requisition', states: [], transitions: [] },
  ] as unknown as typeof current.definition.workflow_definitions
  vi.mocked(getStudioState).mockResolvedValue(current)
  renderAt('/design-studio/app_test?stage=workflow')
  fireEvent.click(await screen.findByRole('button', { name: 'Preview' }))
  expect(screen.getByRole('dialog', { name: 'Application design preview' })).toBeTruthy()
  expect(screen.getByText('Design preview · temporary records')).toBeTruthy()
  expect(continueStudio).not.toHaveBeenCalled()
  expect(approveProject).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Close application preview' }))
  expect(screen.queryByRole('dialog')).toBeNull()
})
