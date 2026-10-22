// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, render } from '@testing-library/react'
import { useEffect } from 'react'

vi.hoisted(() => {
  const bootstrap = document.createElement('script')
  bootstrap.id = 'studio-bootstrap'
  bootstrap.type = 'application/json'
  bootstrap.textContent = JSON.stringify({
    mode: 'preview',
    app: {
      name: 'Purchasing',
      roles: { buyer: 'Buyer' },
      workflows: [],
      entities: [
        {
          id: 'supplier',
          name: 'Supplier',
          attributes: [
            {
              id: 'number',
              name: 'Number',
              type: 'integer',
              required: true,
              key: true,
              value_source: 'system_generated',
            },
          ],
        },
        { id: 'order', name: 'Order', attributes: [] },
      ],
      references: [
        {
          source: 'order',
          target: 'supplier',
          field: 'supplier_number',
          relationship_id: 'order_supplier',
          target_key: 'number',
          enforcement: 'foreign_key',
          required: true,
        },
      ],
    },
  })
  document.head.appendChild(bootstrap)
})

import { StudioProvider, useStudio, type Studio } from '../../../../scripts/studio-sdk'

afterEach(() => cleanup())

it('creates and updates linked records sequentially before React rerenders', async () => {
  let sdk: Studio | undefined
  function Probe() {
    const current = useStudio()
    useEffect(() => {
      sdk = current
    }, [current])
    return <p>{current.app.user?.name}</p>
  }
  render(
    <StudioProvider>
      <Probe />
    </StudioProvider>,
  )
  await act(async () => {
    const sameRender = sdk!
    const supplier = await sameRender.createRecord('supplier', { name: 'Fictional supplier' })
    expect(supplier.data.number).toBe(1)
    const order = await sameRender.createRecord(
      'order',
      { amount: 10 },
      { order_supplier: supplier.id },
    )
    expect(order.data.supplier_number).toBe(1)
    const changed = await sameRender.updateRecord(
      'order',
      order.id,
      { ...order.data, amount: 20 },
      1,
    )
    expect(changed.revision).toBe(2)
    await expect(sameRender.updateRecord('order', order.id, { amount: 30 }, 1)).rejects.toThrow(
      'Record has changed',
    )
  })
  expect(sdk?.records.order[0].data.amount).toBe(20)
  expect(sdk?.app.user?.role).toBe('buyer')
})
