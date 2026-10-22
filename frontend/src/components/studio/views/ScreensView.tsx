import type { ViewProps } from './types'
import { ScreenWorkbench } from './ScreenWorkbench'
import { useState } from 'react'
import { ApplicationPreviewDialog } from './ApplicationPreviewDialog'
import { ApplicationStructure } from './ApplicationStructure'
import { ThemePicker } from './ThemePicker'

/** Review the application itself: what is proposed, then every screen as each role would use it. Visual resources never decide
 *  business scope. */
export function ScreensView({
  studio,
  refresh,
  access,
  designRequest,
  onDesignRequestHandled,
  recent,
  ask,
  act,
  busy,
}: ViewProps) {
  const [expanded, setExpanded] = useState(false)
  const definition = studio.definition
  return (
    <div className="sw-screens">
      <ThemePicker definition={definition} act={act} disabled={busy || !access?.can.edit} />
      <ApplicationStructure definition={definition} notSetUp={studio.execution_gaps?.length ?? 0} />
      <ScreenWorkbench
        definition={definition}
        refresh={refresh}
        onExpand={() => setExpanded(true)}
        canGenerate={access?.can.edit ?? false}
        recent={recent}
        ask={ask}
        designRequest={designRequest}
        onDesignRequestHandled={onDesignRequestHandled}
      />
      {expanded ? (
        <ApplicationPreviewDialog
          definition={studio.definition}
          refresh={refresh}
          onClose={() => setExpanded(false)}
        />
      ) : null}
    </div>
  )
}
