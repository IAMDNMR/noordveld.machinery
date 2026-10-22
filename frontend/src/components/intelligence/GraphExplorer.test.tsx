// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { GraphExplorer } from './GraphExplorer'
import { evidenceGraph } from './graphModel'
afterEach(cleanup)
it('lets users inspect real records, filter relationship types and zoom the graph', () => {
  const open = vi.fn()
  const view = evidenceGraph([
    {
      entity: 'NVM-1010-AT',
      entity_kind: 'PART',
      relationship: 'IN_CATEGORY',
      target: 'Bucket',
      target_kind: 'CATEGORY',
      data_class: 'REAL',
    },
    {
      entity: 'NVM-1010-AT',
      entity_kind: 'PART',
      relationship: 'FITS',
      target: 'NV-3200',
      target_kind: 'MACHINE',
      data_class: 'REAL',
    },
  ])
  render(<GraphExplorer view={view} onOpen={open} />)
  fireEvent.click(screen.getByRole('button', { name: 'Investigate part' }))
  expect(open).toHaveBeenCalledWith('NVM-1010-AT')
  fireEvent.change(screen.getByRole('combobox', { name: 'Relationship type' }), {
    target: { value: 'FITS' },
  })
  expect(screen.queryByRole('button', { name: 'Category: Bucket' })).toBeNull()
  expect(screen.getByText('2 records · 1 connection')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Machine: NV-3200' }))
  expect(screen.getByRole('heading', { name: 'NV-3200' })).toBeTruthy()
  const before = screen.getByRole('button', { name: 'Zoom in graph' }).parentElement?.textContent
  fireEvent.click(screen.getByRole('button', { name: 'Zoom in graph' }))
  expect(screen.getByRole('button', { name: 'Zoom in graph' }).parentElement?.textContent).not.toBe(
    before,
  )
})
