import type { ApplicationDefinition } from '../../../api/applicationDefinition'
import type { ViewProps } from './types'
import './ThemePicker.css'

const COLOURS = [
  ['#24583e', 'Forest green'],
  ['#245f8b', 'Ocean blue'],
  ['#5b4bb1', 'Indigo'],
  ['#0c6b70', 'Teal'],
  ['#9a4f28', 'Copper'],
  ['#37475b', 'Slate'],
] as const

export function ThemePicker({
  definition,
  act,
  disabled,
}: {
  definition: ApplicationDefinition
  act: ViewProps['act']
  disabled: boolean
}) {
  const colour = definition.theme.primary.toLowerCase()
  return (
    <div className="studio-theme-picker">
      <label>
        <span
          className="studio-theme-picker__swatch"
          style={{ backgroundColor: colour }}
          aria-hidden="true"
        />
        Application colour
        <select
          aria-label="Application colour"
          value={colour}
          disabled={disabled}
          onChange={(event) =>
            act(
              [{ type: 'set_theme', primary: event.target.value }],
              'Update the application colour.',
            )
          }
        >
          {!COLOURS.some(([value]) => value === colour) ? (
            <option value={colour}>Current colour</option>
          ) : null}
          {COLOURS.map(([value, name]) => (
            <option key={value} value={value}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <span>Saved with your application</span>
    </div>
  )
}
