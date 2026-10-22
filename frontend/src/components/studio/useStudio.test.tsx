// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import { getStudioState, type StudioState } from '../../api/studio'
import { emptyDefinition } from './model/applicationDefinition'
import { useStudio } from './useStudio'

vi.mock('../../api/studio', async (original) => ({
  ...(await original<typeof import('../../api/studio')>()),
  ensureOrganization: vi.fn(),
  getStudioState: vi.fn(),
  getStudioAccess: vi.fn(async () => null),
}))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})
const state = (id: string): StudioState =>
  ({
    definition: { ...emptyDefinition(), id },
    revision: 1,
    base_sha256: id,
    compile: null,
  }) as StudioState
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

it('keeps the newer project when an earlier open request finishes late', async () => {
  const first = deferred<StudioState>()
  vi.mocked(getStudioState).mockImplementation((id) =>
    id === 'first' ? first.promise : Promise.resolve(state(id)),
  )
  const { result } = renderHook(() => useStudio(false))
  let opening!: Promise<void>
  act(() => {
    opening = result.current.open('first')
  })
  await act(async () => {
    await result.current.open('second')
  })
  await act(async () => {
    first.resolve(state('first'))
    await opening
  })
  expect(result.current.projectId).toBe('second')
  expect(result.current.studio?.definition.id).toBe('second')
})
