import type { ResultItem } from '../../api/intelligenceTypes'
import { NOT_AVAILABLE, ProvenanceBadge } from './provenance'

/** Compare recorded availability without inferring stock or delivery promises. */
export function AvailabilityTable({ items }: { items: ResultItem[] }) {
  const columns = [...new Set(items.flatMap((item) => item.facts.map((fact) => fact.label)))]
  return (
    <div
      className="spark-availability"
      role="region"
      aria-label="Availability records"
      // Keyboard users need focus here to scroll the table horizontally.
      // oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
    >
      <table>
        <caption>Recorded availability · confirm current stock before ordering</caption>
        <thead>
          <tr>
            <th scope="col">Location or partner</th>
            {columns.map((label) => (
              <th scope="col" key={label}>
                {label}
              </th>
            ))}
            <th scope="col">Data source</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.kind}-${item.key}`}>
              <th scope="row">
                {item.title}
                {item.subtitle ? <span>{item.subtitle}</span> : null}
                {item.groups.map((group) => (
                  <span key={group.label}>
                    {group.label}: {group.values.join(', ') || NOT_AVAILABLE}
                  </span>
                ))}
              </th>
              {columns.map((label) => (
                <td key={label}>
                  {item.facts.find((fact) => fact.label === label)?.value ?? NOT_AVAILABLE}
                </td>
              ))}
              <td>
                <ProvenanceBadge value={item.data_class} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
