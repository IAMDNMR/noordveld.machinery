// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { QuestionCatalog } from './QuestionCatalog'

const GROUPS = [
  { category: 'Parts', note: null, questions: ['Find part A', 'Find part B'] },
  { category: 'Orders', note: 'Sign in for these.', questions: ['Where is my order?'] },
]

describe('question catalog', () => {
  afterEach(cleanup)

  it('shows every question by category, as selectable options', () => {
    render(<QuestionCatalog groups={GROUPS} onAsk={() => {}} />)
    expect(screen.getByText('3 questions · choose one to run it')).toBeTruthy()
    expect(within(screen.getByRole('list', { name: 'Parts questions' })).getAllByRole('button').map((b) => b.textContent)).toEqual(['Find part A', 'Find part B'])
    expect(within(screen.getByRole('list', { name: 'Orders questions' })).getByRole('button', { name: 'Where is my order?' })).toBeTruthy()
    expect(screen.getByText('Sign in for these.')).toBeTruthy()
  })

  it('narrows to one category and back to all', () => {
    render(<QuestionCatalog groups={GROUPS} onAsk={() => {}} />)
    const filters = screen.getByRole('group', { name: 'Question categories' })
    fireEvent.click(within(filters).getByRole('button', { name: 'Orders' }))
    expect(within(filters).getByRole('button', { name: 'Orders' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.queryByRole('list', { name: 'Parts questions' })).toBeNull()
    fireEvent.click(within(filters).getByRole('button', { name: 'All' }))
    expect(screen.getByRole('list', { name: 'Parts questions' })).toBeTruthy()
  })

  it('runs the chosen question as it is written', () => {
    const asked: string[] = []
    render(<QuestionCatalog groups={GROUPS} onAsk={(q) => asked.push(q)} />)
    fireEvent.click(screen.getByRole('button', { name: 'Find part B' }))
    expect(asked).toEqual(['Find part B'])
  })
})
