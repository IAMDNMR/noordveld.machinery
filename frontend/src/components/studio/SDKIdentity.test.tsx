// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

afterEach(() => {
  cleanup()
  document.getElementById('studio-bootstrap')?.remove()
})

it('preview sign-in uses identity IDs and refuses a role ID without losing the current user', async () => {
  const bootstrap = document.createElement('script')
  bootstrap.id = 'studio-bootstrap'
  bootstrap.type = 'application/json'
  bootstrap.textContent = JSON.stringify({
    mode: 'preview',
    app: {
      name: 'Synthetic service test',
      entities: [],
      workflows: [],
      roles: { role_coordinator: 'Coordinator', role_technician: 'Technician' },
    },
  })
  document.head.append(bootstrap)
  const { StudioProvider, useStudio } = await import('../../../scripts/studio-sdk')
  function IdentityTest() {
    const { user, users, signIn, error } = useStudio()
    return (
      <>
        <output aria-label="Current identity">{user?.id}</output>
        <output aria-label="Current role">{user?.role}</output>
        <p role="alert">{error}</p>
        <button onClick={() => void signIn('role_technician').catch(() => {})}>Use role ID</button>
        <button onClick={() => void signIn(users[1].id)}>Use listed identity</button>
      </>
    )
  }
  render(
    <StudioProvider>
      <IdentityTest />
    </StudioProvider>,
  )
  const initialIdentity = screen.getByLabelText('Current identity').textContent
  fireEvent.click(screen.getByRole('button', { name: 'Use role ID' }))
  await waitFor(() =>
    expect(screen.getByRole('alert').textContent).toContain('Unknown application identity'),
  )
  expect(screen.getByLabelText('Current identity').textContent).toBe(initialIdentity)
  fireEvent.click(screen.getByRole('button', { name: 'Use listed identity' }))
  await waitFor(() =>
    expect(screen.getByLabelText('Current role').textContent).toBe('role_technician'),
  )
  expect(screen.getByLabelText('Current identity').textContent).not.toBe('role_technician')
})
