import type { ViewProps } from './types'
import { ScreenWorkbench } from './ScreenWorkbench'
import { liveDemoUrl } from '../../../api/studio'
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
  const definition = studio.definition
  return (
    <div className="sw-screens">
      <ThemePicker definition={definition} act={act} disabled={busy || !access?.can.edit} />
      <ApplicationStructure definition={definition} notSetUp={studio.execution_gaps?.length ?? 0} />
      <ScreenWorkbench
        definition={definition}
        refresh={refresh}
        fullScreenHref={liveDemoUrl(definition.id)}
        canGenerate={access?.can.edit ?? false}
        recent={recent}
        ask={ask}
        designRequest={designRequest}
        onDesignRequestHandled={onDesignRequestHandled}
      />
    </div>
  )
}
