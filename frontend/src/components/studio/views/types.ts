import type { StageKey, StudioAccess, StudioState } from '../../../api/studio'

/** What every stage view receives. Views never hold their own copy of the project: they render `studio.definition` and change it through `act` or `ask`. */
export type ViewProps = {
  studio: StudioState
  /** What this person may do in this project (null while it loads). Views offer only authorized actions and say why the others are unavailable. */
  access: StudioAccess | null
  recent: ReadonlySet<string>
  busy: boolean
  /** Put a sentence in the assistant's composer for the person to send or edit. */
  ask: (text: string) => void
  /** Answer an open question in the conversation: the assistant records the reply against that question. */
  answer: (questionId: string) => void
  /** Send a sentence to the assistant right away. */
  say: (text: string) => void
  /** A direct change with the same typed actions the assistant uses (no language model). */
  act: (actions: Record<string, unknown>[], note?: string) => void
  go: (stage: StageKey) => void
  select: (reference: string | null) => void
  selection: string | null
  /** Approve the saved revision. Returns an error message, or null on success. A separate approver is enforced by the server. */
  approve: (
    scope: 'process' | 'design',
    acknowledged: string[],
    comment: string,
  ) => Promise<string | null>
  /** Let the Studio settle, in one revision, the findings whose fix follows from the design. Returns what it changed. */
  resolve?: () => Promise<string[] | null>
  /** Generate screens from the approved process. Returns an error message, or null on success. */
  refresh: (compile?: boolean) => Promise<unknown>
  /** Signed-in person, for explaining why an action may be refused. */
  userName: string
  /** Changes each time the assistant (or a button) asks for the application to be generated now. */
  autorun?: number
  designRequest?: { id: number; projectId: string; brief: string } | null
  onDesignRequestHandled?: () => void
}
