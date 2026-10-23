import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MessageSquarePlus } from 'lucide-react'
import type { ApplicationDefinition } from '../../../api/applicationDefinition'
import type { StudioState } from '../../../api/studio'
import { GeneratedFrontendView } from './GeneratedFrontendView'
import './ScreenWorkbench.css'

type Route = { page: string; id?: string | null; entity?: string | null }
type Entry = { section: string; label: string; target: Route; count: number; active: boolean }
type PreviewState = { role: string; roleName: string; route: Route; title: string; menu: Entry[] }

const isEntry = (value: unknown): value is Entry =>
  !!value &&
  typeof (value as Entry).label === 'string' &&
  typeof (value as Entry).section === 'string' &&
  typeof (value as Entry).target?.page === 'string'

/** Read what the preview reports; anything that is not exactly this shape is ignored. */
function readState(data: unknown): PreviewState | null {
  const message = data as { type?: string } & Partial<PreviewState>
  if (message?.type !== 'studio:state' || typeof message.role !== 'string') return null
  if (typeof message.route?.page !== 'string' || !Array.isArray(message.menu)) return null
  return {
    role: message.role,
    roleName: typeof message.roleName === 'string' ? message.roleName : message.role,
    route: message.route,
    title: typeof message.title === 'string' ? message.title : '',
    menu: message.menu.filter(isEntry),
  }
}

/** The preview with a screen explorer beside it. The explorer lists exactly the screens the running preview offers the chosen role,
 *  follows where the preview is, and returns to the same role and screen after the assistant changes the design. */
export function ScreenWorkbench({
  definition,
  refresh,
  fullScreenHref,
  canGenerate,
  recent,
  ask,
  designRequest,
  onDesignRequestHandled,
}: {
  definition: StudioState['definition']
  refresh?: () => Promise<unknown>
  fullScreenHref?: string
  canGenerate: boolean
  /** Ids the assistant just changed. */
  recent: ReadonlySet<string>
  ask: (text: string) => void
  designRequest?: { id: number; projectId: string; brief: string } | null
  onDesignRequestHandled?: () => void
}) {
  const frame = useRef<HTMLIFrameElement | null>(null)
  const seen = useRef<MessageEventSource | null>(null)
  const remembered = useRef<{ role: string; route: Route } | null>(null)
  const [state, setState] = useState<PreviewState | null>(null)

  const send = useCallback((message: Record<string, unknown>) => {
    frame.current?.contentWindow?.postMessage(message, '*')
  }, [])

  useEffect(() => {
    const listen = (event: MessageEvent) => {
      if (!frame.current || event.source !== frame.current.contentWindow) return
      const next = readState(event.data)
      if (!next) return
      if (event.source !== seen.current) {
        // A new preview document (first load, or the design changed): hide its own menu and go back to where the person was.
        seen.current = event.source
        send({ type: 'studio:layout', embedded: true })
        const was = remembered.current
        if (
          was &&
          (was.role !== next.role ||
            was.route.page !== next.route.page ||
            was.route.id !== next.route.id)
        )
          send({ type: 'studio:go', role: was.role, route: was.route })
        else remembered.current = { role: next.role, route: next.route }
      } else remembered.current = { role: next.role, route: next.route }
      setState(next)
    }
    window.addEventListener('message', listen)
    return () => window.removeEventListener('message', listen)
  }, [send])

  const roles = definition.business.roles
  const working = useMemo(
    () => new Set(definition.workflow_definitions.flatMap((w) => w.states.map((s) => s.role_id))),
    [definition],
  )
  // Menu entries whose process or record the assistant just changed.
  const changed = useMemo(() => {
    const ids = new Set<string>()
    for (const workflow of definition.workflow_definitions)
      if (recent.has(workflow.id) || workflow.states.some((s) => recent.has(s.id)))
        ids.add(workflow.id)
    for (const entity of definition.business.entities) if (recent.has(entity.id)) ids.add(entity.id)
    return ids
  }, [definition, recent])

  const sections = useMemo(() => {
    const groups = new Map<string, Entry[]>()
    for (const entry of state?.menu ?? [])
      groups.set(entry.section, [...(groups.get(entry.section) ?? []), entry])
    return [...groups]
  }, [state])

  return (
    <div className="sw-workbench">
      <aside className="sw-explorer" aria-label="Screen explorer">
        <label className="sw-explorer__role">
          <span>View the application as</span>
          <select
            value={state?.role ?? ''}
            disabled={!state}
            onChange={(event) =>
              send({ type: 'studio:go', role: event.target.value, route: { page: 'home' } })
            }
          >
            {!state ? <option value="">Loading…</option> : null}
            {roles.map((role) => (
              <option key={role.id} value={role.id}>
                {role.name}
                {working.has(role.id) ? '' : ' (no steps yet)'}
              </option>
            ))}
          </select>
        </label>
        {state ? (
          <nav aria-label={`Screens for ${state.roleName}`}>
            {sections.map(([section, entries]) => (
              <div key={section || 'general'} className="sw-explorer__group">
                {section ? <small>{section}</small> : null}
                {entries.map((entry) => (
                  <button
                    type="button"
                    key={`${entry.target.page}:${entry.target.id ?? ''}`}
                    aria-current={entry.active ? 'page' : undefined}
                    onClick={() => send({ type: 'studio:go', route: entry.target })}
                  >
                    <span>{entry.label}</span>
                    {entry.target.id && changed.has(entry.target.id) ? (
                      <em>Updated</em>
                    ) : entry.count ? (
                      <i>{entry.count}</i>
                    ) : null}
                  </button>
                ))}
              </div>
            ))}
          </nav>
        ) : (
          <p className="sw-muted" role="status">
            Loading the screens…
          </p>
        )}
        {state ? (
          <button
            type="button"
            className="sw-button sw-explorer__ask"
            onClick={() =>
              ask(`Change the “${state.title || 'this'}” screen for ${state.roleName}: `)
            }
          >
            <MessageSquarePlus size={14} aria-hidden="true" /> Ask the assistant about this screen
          </button>
        ) : null}
      </aside>
      <GeneratedFrontendView
        definition={definition as ApplicationDefinition}
        refresh={refresh}
        fullScreenHref={fullScreenHref}
        canGenerate={canGenerate}
        designRequest={designRequest}
        onDesignRequestHandled={onDesignRequestHandled}
        frameRef={frame}
      />
    </div>
  )
}
