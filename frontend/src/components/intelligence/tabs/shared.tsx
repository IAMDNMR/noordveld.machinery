import type { ReactNode } from 'react'
import type { ApiState } from '../../../hooks/useApi'
import { ErrorNotice } from '../Notices'
import { NOT_AVAILABLE } from '../provenance'

/** Loading, error and content for one tab. Each tab fetches only when it is shown. */
export function TabFrame<T>({ state, children, label }: { state: ApiState<T>; children: (data: T) => ReactNode; label: string }) {
  if (state.error) return <ErrorNotice error={state.error} onRetry={state.reload} title={`${label} could not be loaded`} />
  if (!state.data) {
    return (
      <p className="pw-loading" role="status">
        Loading {label.toLowerCase()}…
      </p>
    )
  }
  return <>{children(state.data)}</>
}

/** A label/value list. Missing values read "Not available", never a blank or a zero. */
export function Facts({ rows }: { rows: [string, ReactNode | null | undefined][] }) {
  return (
    <dl className="pw-facts">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd className={value === null || value === undefined || value === '' ? 'is-missing' : undefined}>{value === null || value === undefined || value === '' ? NOT_AVAILABLE : value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="pw-empty">{children}</p>
}

export const place = (city: string | null, country: string | null): string | null => [city, country].filter(Boolean).join(', ') || null
export const yesNo = (value: boolean | null): string | null => (value === null ? null : value ? 'Yes' : 'No')
