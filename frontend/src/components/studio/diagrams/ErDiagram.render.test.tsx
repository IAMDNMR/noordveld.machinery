// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ErDiagram } from './ErDiagram'

import type { BusinessEntity } from '../../../api/applicationDefinition'

afterEach(cleanup)
const entity = (id: string, name: string, target?: string): BusinessEntity => ({
  id,
  name,
  attributes: [{ id: 'number', name: 'Number', type: 'integer', key: true, required: true }],
  relationships: target
    ? [
        {
          id: `to_${target}`,
          name: 'Belongs to',
          target,
          cardinality: 'many_to_one',
          required: true,
        },
      ]
    : [],
})
const entities = [
  entity('order', 'Order', 'customer'),
  entity('customer', 'Customer'),
  entity('line', 'Order line', 'order'),
]

it('renders every saved connector before any entity is selected and keeps focus mode explicit', () => {
  const select = vi.fn()
  const view = render(
    <ErDiagram
      entities={entities}
      selectedId={null}
      onSelect={select}
      zoom={1}
      recent={new Set()}
    />,
  )
  expect(view.container.querySelectorAll('.sw-er__edge > path')).toHaveLength(2)
  expect(
    [...view.container.querySelectorAll('.sw-er__edge > path')].every(
      (path) => path.getAttribute('marker-start') && path.getAttribute('marker-end'),
    ),
  ).toBe(true)
  fireEvent.keyDown(screen.getByRole('button', { name: 'Customer, 1 attributes' }), {
    key: 'Enter',
  })
  expect(select).toHaveBeenCalledWith('customer')
  view.rerender(
    <ErDiagram
      entities={entities}
      selectedId="customer"
      showAll={false}
      onSelect={select}
      zoom={1}
      recent={new Set()}
    />,
  )
  expect(view.container.querySelectorAll('.sw-er__edge > path')).toHaveLength(1)
})
