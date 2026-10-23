// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { RolesView } from './RolesView'
import type { ViewProps } from './types'
afterEach(cleanup)
it('includes owner access and denies step access when its permission is absent', () => {
  const studio = {
    definition: {
      business: {
        roles: [
          { id: 'owner', name: 'Steward', permissions: [], responsibilities: [] },
          { id: 'worker', name: 'Worker', permissions: [], responsibilities: [] },
        ],
        entities: [{ id: 'record', name: 'Customer', owner_role_id: 'owner' }],
      },
      workflow_definitions: [
        {
          states: [
            {
              id: 'edit',
              label: 'Edit',
              role_id: 'worker',
              permission: 'customer.edit',
              writes_entity_ids: ['record'],
            },
          ],
        },
      ],
    },
  }
  render(<RolesView {...({ studio, recent: new Set(), ask: vi.fn() } as unknown as ViewProps)} />)
  const row = screen.getByRole('row', { name: /Customer/ })
  // The owner creates, reads and updates its record; nobody deletes (the generated application keeps every record); a worker whose
  // step permission is missing has no access at all.
  expect(within(row).getByText('can create, read, update')).toBeTruthy()
  expect(within(row).getByText('no access')).toBeTruthy()
  expect(within(row).queryByText(/delete/i)).toBeNull()
})
