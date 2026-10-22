// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { useEffect } from 'react'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { StudioProvider, useStudio, type Studio } from '../../../../scripts/studio-sdk'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('uses server sessions, exact write revisions and server-owned workflow outcomes', async () => {
  const user = { id: 'demo:buyer', name: 'Buyer', role: 'buyer', tenant: 'demo' }
  const requests: { path: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init: RequestInit) => {
      const body = init.body ? (JSON.parse(String(init.body)) as unknown) : undefined
      requests.push({ path, body })
      if (path.endsWith('/advance'))
        return {
          ok: false,
          json: async () => ({ error: 'Only the approver can perform this step.' }),
        }
      const value =
        path === '/api/demo-users'
          ? [user]
          : path === '/api/application'
            ? {
                name: 'Purchasing',
                entities: [{ id: 'request', name: 'Request', attributes: [], writable: true }],
                workflows: [],
                roles: { buyer: 'Buyer' },
                user: { actor: user.id, role: user.role, tenant: user.tenant },
              }
            : path.startsWith('/api/records/') && init.method === 'GET'
              ? []
              : path === '/api/instances'
                ? []
                : path.startsWith('/api/records/')
                  ? { id: 'record-1', revision: 2, data: { amount: 10 } }
                  : { ok: true }
      return { ok: true, json: async () => value }
    }),
  )
  let sdk: Studio | undefined
  function Probe() {
    const current = useStudio()
    useEffect(() => {
      sdk = current
    }, [current])
    return <p>{current.user?.name ?? 'Choose an identity'}</p>
  }
  render(
    <StudioProvider>
      <Probe />
    </StudioProvider>,
  )
  await waitFor(() => expect(sdk?.users).toHaveLength(1))
  await act(async () => {
    await sdk?.signIn(user.id)
  })
  expect(sdk?.user?.id).toBe(user.id)
  expect(sdk?.user?.name).toBe('Buyer')
  await act(async () => {
    await sdk?.updateRecord('request', 'record-1', { amount: 10 }, 1)
  })
  expect(
    requests.find((request) => request.path === '/api/records/request/record-1')?.body,
  ).toEqual({ data: { amount: 10 }, expected_revision: 1 })
  await act(async () => {
    await expect(sdk!.advanceWorkflow('work-1', 3, { request: 'record-1' })).rejects.toThrow(
      'Only the approver',
    )
  })
  expect(requests.find((request) => request.path.endsWith('/advance'))?.body).toEqual({
    expected_revision: 3,
    links: { request: 'record-1' },
  })
  expect(sdk?.error).toBe('Only the approver can perform this step.')
})

it('maps selected record IDs to the declared relationship fields', async () => {
  const requests: { path: string; body: unknown }[] = []
  const user = { id: 'buyer-1', name: 'Buyer', role: 'buyer', tenant: 'demo' }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init: RequestInit) => {
      const body = init.body ? (JSON.parse(String(init.body)) as unknown) : undefined
      requests.push({ path, body })
      const value =
        path === '/api/demo-users'
          ? [user]
          : path === '/api/application'
            ? {
                name: 'Purchasing',
                entities: [
                  { id: 'supplier', name: 'Supplier', attributes: [] },
                  { id: 'order', name: 'Order', attributes: [] },
                ],
                workflows: [],
                roles: { buyer: 'Buyer' },
                user,
                references: [
                  {
                    source: 'order',
                    target: 'supplier',
                    field: 'rel_order_supplier',
                    relationship_id: 'rel_order_supplier',
                    target_key: null,
                    enforcement: 'link',
                    required: true,
                  },
                ],
              }
            : path === '/api/records/supplier'
              ? [{ id: 'supplier-uuid', revision: 1, data: { supplier_no: 42 } }]
              : path === '/api/instances' || init.method === 'GET'
                ? []
                : { id: 'order-uuid', revision: 1, data: { amount: 10 } }
      return { ok: true, json: async () => value }
    }),
  )
  let sdk: Studio | undefined
  function Probe() {
    const current = useStudio()
    useEffect(() => {
      sdk = current
    }, [current])
    return <p>{current.loading ? 'Loading' : 'Ready'}</p>
  }
  render(
    <StudioProvider>
      <Probe />
    </StudioProvider>,
  )
  await waitFor(() => expect(sdk?.records.supplier).toHaveLength(1))
  await act(async () => {
    await sdk?.createRecord('order', { amount: 10 }, { supplier: 'supplier-uuid' })
  })
  expect(
    requests.find((request) => request.path === '/api/records/order' && request.body)?.body,
  ).toEqual({
    data: { amount: 10, rel_order_supplier: 'supplier-uuid' },
  })
  await act(async () => {
    await expect(sdk?.createRecord('order', { amount: 10 }, { supplier: '42' })).rejects.toThrow(
      'selected related record is unavailable',
    )
  })
})
