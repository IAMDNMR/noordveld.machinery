// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QuestionInput } from './QuestionInput'
afterEach(cleanup)
it('offers more real examples without hiding the selected topic or losing their action', () => {
  const onAsk = vi.fn()
  const suggestions = Array.from({ length: 6 }, (_, i) => ({
    category: 'Part Discovery',
    question: `Find catalogue part ${i + 1}`,
  }))
  render(<QuestionInput value="" busy={false} onAsk={onAsk} suggestions={suggestions} />)
  expect(screen.queryByRole('button', { name: 'Find catalogue part 6' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'See all 6 questions' }))
  fireEvent.click(screen.getByRole('button', { name: 'Find catalogue part 6' }))
  expect(onAsk).toHaveBeenCalledWith('Find catalogue part 6')
  fireEvent.click(screen.getByRole('button', { name: 'Fewer questions' }))
  expect(screen.queryByRole('button', { name: 'Find catalogue part 6' })).toBeNull()
})
