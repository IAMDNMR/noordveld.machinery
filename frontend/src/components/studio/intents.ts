/** Short spoken or typed replies that mean "do what is waiting". They only ever act on something the person can see on screen. */
const FILLER = String.raw`(?:(?:yes|yeah|yep|sure|okay|ok|please|right|alright)\W+)*`
const APPLY = new RegExp(
  `^${FILLER}(?:apply(?:\\s+(?:it|that|this|the\\s+changes?|the\\s+change|the\\s+proposal))?|go\\s+ahead(?:\\s+and\\s+apply(?:\\s+(?:it|that|the\\s+changes?))?)?|confirm(?:\\s+it)?|do\\s+it|looks\\s+good|that\\s+looks\\s+good|that'?s\\s+right|yes|yeah|yep|sure|okay|ok)\\W*$`,
  'i',
)
const REFUSAL = String.raw`(?:(?:no|nope|nah|please)\W+)*`
const DISMISS = new RegExp(
  `^${REFUSAL}(?:no|nope|dismiss(?:\\s+it)?|cancel(?:\\s+that)?|discard(?:\\s+it)?|not\\s+now|skip(?:\\s+it)?|never\\s*mind)\\W*$`,
  'i',
)
const UNDO =
  /^(?:please\s+)?(?:undo(?:\s+(?:that|the\s+last\s+change))?|revert(?:\s+that)?|go\s+back|take\s+that\s+back)\W*$/i
const STOP = /^(?:stop(?:\s+talking)?|be\s+quiet|quiet|enough|hold\s+on|wait)\W*$/i

export type LocalIntent = 'apply' | 'dismiss' | 'undo' | 'stop' | null

/** `waiting` is the number of proposals on screen that have not been answered. "Yes" with nothing waiting is an answer to the assistant, not a command. */
export function localIntent(text: string, waiting: number): LocalIntent {
  const clean = text.trim()
  if (STOP.test(clean)) return 'stop'
  if (UNDO.test(clean)) return 'undo'
  if (waiting === 1 && APPLY.test(clean)) return 'apply'
  if (waiting >= 1 && DISMISS.test(clean)) return 'dismiss'
  return null
}
