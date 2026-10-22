import { describe, expect, it } from 'vitest'
import { localIntent } from './intents'

describe('spoken confirmations', () => {
  it('apply what is waiting, in the ways people say it', () => {
    for (const text of [
      'Yes, apply it.',
      'apply',
      'Apply that',
      'yes please apply the changes',
      'go ahead',
      'Looks good!',
      'okay',
      'Yes.',
      'confirm it',
      'Go ahead and apply the change.',
      'Please apply the change.',
    ])
      expect(localIntent(text, 1), text).toBe('apply')
  })
  it('never applies when nothing is waiting, or when two proposals are', () => {
    expect(localIntent('yes', 0)).toBeNull()
    expect(localIntent('apply it', 2)).toBeNull()
  })
})
