import type { SparkChart, SparkPresentation, SparkTable } from '../../api/spark'
import { BarChart } from '../cine/Cine'

type Format = NonNullable<SparkPresentation['intelligence']>
const FORMATS: readonly Format[] = ['text', 'table', 'cards', 'chart', 'graph', 'choices']

/**
 * The presentation the server chose, checked before use. A missing or malformed block (an older saved turn, a partial
 * response) falls back: a table or chart without its data becomes text, and an unknown format means the classic layout.
 */
export function readPresentation(value: SparkPresentation | null | undefined): {
  format: Format | undefined
  table: SparkTable | null
  chart: SparkChart | null
} {
  const table =
    value?.table &&
    Array.isArray(value.table.columns) &&
    Array.isArray(value.table.rows) &&
    value.table.rows.every(
      (row) => Array.isArray(row.cells) && row.cells.length === value.table!.columns.length - 1,
    )
      ? value.table
      : null
  const chart =
    value?.chart &&
    Array.isArray(value.chart.rows) &&
    value.chart.rows.length > 1 &&
    value.chart.rows.every((row) => Number.isFinite(row.value))
      ? value.chart
      : null
  const wanted = FORMATS.includes(value?.intelligence as Format) ? value?.intelligence : undefined
  const format =
    (wanted === 'table' && !table) || (wanted === 'chart' && !chart)
      ? 'text'
      : (wanted ?? undefined)
  return { format: format ?? undefined, table, chart }
}

/** Records with the same attributes, aligned. A part's number opens it over the conversation. */
export function RecordTable({
  table,
  onOpenPart,
  label,
}: {
  table: SparkTable
  onOpenPart: (partNumber: string) => void
  label: string
}) {
  const [first, ...rest] = table.columns
  return (
    <div className="spark-table" role="region" aria-label={label}>
      <table>
        <thead>
          <tr>
            <th scope="col">{first}</th>
            {rest.map((column) => (
              <th scope="col" key={column}>
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">
                {row.part_number ? (
                  <button type="button" onClick={() => onOpenPart(row.part_number!)}>
                    {row.title}
                  </button>
                ) : (
                  row.title
                )}
              </th>
              {row.cells.map((cell, index) => (
                <td key={rest[index]} data-label={rest[index]}>
                  {cell ?? <span className="spark-table__missing">Not recorded</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Recorded numbers across records, drawn as bars with their values; the data behind it is the records themselves. */
export function RecordChart({ chart }: { chart: SparkChart }) {
  return (
    <figure className="spark-chart">
      <figcaption>{chart.metric}</figcaption>
      <BarChart label={chart.metric} rows={chart.rows} />
    </figure>
  )
}
