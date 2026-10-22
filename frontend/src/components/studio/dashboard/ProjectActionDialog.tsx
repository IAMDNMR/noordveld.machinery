import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import type { DashboardProject, ProjectAction } from '../../../api/studioProjects'

export function ProjectActionDialog({
  project,
  action,
  busy,
  error,
  onClose,
  onConfirm,
}: {
  project: DashboardProject
  action: ProjectAction
  busy: boolean
  error: string | null
  onClose: () => void
  onConfirm: (name?: string) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [confirmation, setConfirmation] = useState('')
  useEffect(() => {
    const node = dialog.current
    node?.showModal()
    return () => node?.close()
  }, [])
  const title =
    action === 'rename'
      ? 'Rename project'
      : action === 'trash'
        ? 'Move project to Trash?'
        : action === 'archive'
          ? 'Archive project?'
          : action === 'delete'
            ? 'Permanently delete project?'
            : 'Restore project?'
  return (
    <dialog
      ref={dialog}
      className="sd-dialog"
      onCancel={(event) => {
        event.preventDefault()
        if (!busy) onClose()
      }}
      aria-labelledby="project-action-title"
    >
      <form
        onSubmit={(event) => {
          event.preventDefault()
          const data = new FormData(event.currentTarget)
          if (action === 'delete' && confirmation !== project.name) return
          onConfirm(action === 'delete' ? confirmation : data.get('name')?.toString().trim())
        }}
      >
        <header>
          <h2 id="project-action-title">{title}</h2>
          <button type="button" disabled={busy} onClick={onClose} aria-label="Close dialog">
            <X size={20} />
          </button>
        </header>
        {action === 'rename' ? (
          <label>
            Project name
            <input name="name" defaultValue={project.name} required maxLength={120} />
          </label>
        ) : (
          <p>
            {action === 'trash'
              ? 'The project will leave your active workspace. Its design and revision history stay saved, and you can restore it from Trash.'
              : action === 'archive'
                ? 'Keep this project for reference without cluttering your active workspace. You can restore it anytime.'
                : action === 'delete'
                  ? 'This deletes the project, all revision history, saved code downloads and test results from Studio. You cannot undo this. Separate application databases and backups are not erased.'
                  : 'Return this project to its previous workspace so you can continue working.'}
          </p>
        )}
        <p className="sd-dialog-project">
          {project.name} · Revision {project.revision}
        </p>
        {action === 'delete' && (
          <label>
            Type the project name to confirm
            <input
              name="confirmation"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="off"
              required
            />
          </label>
        )}
        {error && (
          <p role="alert" className="sd-danger">
            {error}
          </p>
        )}
        <footer>
          <button type="button" disabled={busy} onClick={onClose}>
            Cancel
          </button>
          <button
            className={`sd-primary ${action === 'trash' || action === 'delete' ? 'sd-primary--danger' : ''}`}
            disabled={busy || (action === 'delete' && confirmation !== project.name)}
          >
            {busy
              ? 'Saving…'
              : action === 'rename'
                ? 'Save name'
                : action === 'trash'
                  ? 'Move to Trash'
                  : action === 'archive'
                    ? 'Archive project'
                    : action === 'delete'
                      ? 'Delete permanently'
                      : 'Restore project'}
          </button>
        </footer>
      </form>
    </dialog>
  )
}
