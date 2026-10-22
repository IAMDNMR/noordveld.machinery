import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import type { ApplicationDefinition } from '../../../api/applicationDefinition'
import { GeneratedFrontendView } from './GeneratedFrontendView'
import './ApplicationPreviewDialog.css'

export function ApplicationPreviewDialog({
  definition,
  onClose,
  refresh,
}: {
  definition: ApplicationDefinition
  onClose: () => void
  refresh?: () => Promise<unknown>
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const node = dialog.current
    node?.showModal()
    return () => node?.close()
  }, [])
  return (
    <dialog
      className="studio-preview-dialog"
      ref={dialog}
      aria-label="Application design preview"
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
    >
      <header>
        <div>
          <strong>{definition.metadata.name}</strong>
          <span>Design preview · temporary records</span>
        </div>
        <button type="button" onClick={onClose} aria-label="Close application preview">
          <X size={20} />
        </button>
      </header>
      <GeneratedFrontendView definition={definition} refresh={refresh} previewOnly />
    </dialog>
  )
}
