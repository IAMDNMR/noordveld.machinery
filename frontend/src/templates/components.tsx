import { useState, type ReactNode } from 'react'
import { Check, ImageOff, Search } from 'lucide-react'
import type { SampleRow, TemplateComponent } from '../api/appTemplates'
import { isStatus, label, show, titleOf, tone } from './format'

type Props = {
  component: TemplateComponent
  rows: SampleRow[]
  query: string
  onQuery: (value: string) => void
}

const Chip = ({ value }: { value: SampleRow[string] | undefined }) => (
  <span className={`ta-chip ta-chip--${tone(value)}`}>{show('', value)}</span>
)

function Value({ field, row }: { field: string; row: SampleRow }) {
  return isStatus(field) ? <Chip value={row[field]} /> : <>{show(field, row[field])}</>
}

function Empty({ text }: { text: string }) {
  return <p className="ta-empty">{text}</p>
}

function FilterBar({ query, onQuery, component }: Props) {
  return (
    <label className="ta-filter">
      <Search size={18} aria-hidden="true" />
      <span className="ta-sr">{component.title || 'Search'}</span>
      <input
        value={query}
        onChange={(event) => onQuery(event.target.value)}
        placeholder={component.title || 'Search'}
      />
    </label>
  )
}

function MetricStrip({ component, rows }: Props) {
  const field = component.group_by
  if (!field) return null
  const counts = new Map<string, number>()
  for (const row of rows)
    counts.set(String(row[field] ?? '—'), (counts.get(String(row[field] ?? '—')) ?? 0) + 1)
  if (!counts.size) return <Empty text="No records yet." />
  return (
    <div className="ta-metrics">
      {[...counts].map(([key, count]) => (
        <div key={key} className={`ta-metric ta-metric--${tone(key)}`}>
          <strong>{count}</strong>
          <span>{key}</span>
        </div>
      ))}
    </div>
  )
}

function ProductGrid({ component, rows }: Props) {
  if (!rows.length) return <Empty text="Nothing matches yet." />
  const fields = component.fields.filter((field) => field !== 'image')
  const [title, ...rest] = fields
  return (
    <div className="ta-products">
      {rows.map((row) => (
        <article key={String(row.id)} className="ta-product">
          {component.fields.includes('image') ? (
            <div className="ta-product__image" aria-hidden="true">
              <ImageOff size={28} />
            </div>
          ) : null}
          <h4>{show(title, row[title])}</h4>
          {rest.map((field) => (
            <p key={field} className={field === 'price' ? 'ta-price' : undefined}>
              <Value field={field} row={row} />
            </p>
          ))}
        </article>
      ))}
    </div>
  )
}

function DataTable({ component, rows }: Props) {
  if (!rows.length) return <Empty text="No records match." />
  return (
    <div className="ta-table-wrap">
      <table className="ta-table">
        <thead>
          <tr>
            {component.fields.map((field) => (
              <th key={field} scope="col">
                {label(field)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.id)}>
              {component.fields.map((field) => (
                <td key={field}>
                  <Value field={field} row={row} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DetailPanel({ component, rows }: Props) {
  const row = rows[0]
  if (!row) return <Empty text="Select a record to see its details." />
  return (
    <dl className="ta-detail">
      {component.fields.map((field) => (
        <div key={field}>
          <dt>{label(field)}</dt>
          <dd>
            <Value field={field} row={row} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

function StatusBoard({ component, rows }: Props) {
  const field = component.group_by
  if (!field) return null
  const columns = [...new Set(rows.map((row) => String(row[field] ?? '—')))]
  if (!columns.length) return <Empty text="No records yet." />
  return (
    <div className="ta-board">
      {columns.map((column) => {
        const items = rows.filter((row) => String(row[field] ?? '—') === column)
        return (
          <section key={column} className="ta-board__column" aria-label={column}>
            <h4>
              <Chip value={column} /> <span className="ta-count">{items.length}</span>
            </h4>
            {items.map((row) => (
              <article key={String(row.id)} className="ta-card">
                <strong>{titleOf(row, component.fields)}</strong>
                {component.fields.slice(1).map((name) => (
                  <span key={name}>{show(name, row[name])}</span>
                ))}
              </article>
            ))}
          </section>
        )
      })}
    </div>
  )
}

function Timeline({ component, rows }: Props) {
  if (!rows.length) return <Empty text="No events yet." />
  const [when, ...rest] = component.fields
  return (
    <ol className="ta-timeline">
      {rows.map((row) => (
        <li key={String(row.id)}>
          <time>{show(when, row[when])}</time>
          <p>{rest.map((field) => show(field, row[field])).join(' · ')}</p>
        </li>
      ))}
    </ol>
  )
}

function TaskQueue({ component, rows }: Props) {
  const [done, setDone] = useState<Set<string>>(new Set())
  const open = rows.filter((row) => !done.has(String(row.id)))
  if (!open.length) return <Empty text="All done. New work appears here." />
  return (
    <ul className="ta-queue">
      {open.map((row) => (
        <li key={String(row.id)} className="ta-task">
          <div>
            <strong>{titleOf(row, component.fields)}</strong>
            <span>
              {component.fields
                .slice(1)
                .map((field) => show(field, row[field]))
                .join(' · ')}
            </span>
          </div>
          {component.group_by ? <Chip value={row[component.group_by]} /> : null}
          <button
            type="button"
            className="ta-button"
            onClick={() => setDone(new Set(done).add(String(row.id)))}
          >
            <Check size={18} aria-hidden="true" /> Complete
          </button>
        </li>
      ))}
    </ul>
  )
}

function ComparisonTable({ component, rows }: Props) {
  if (!rows.length) return <Empty text="No offers to compare yet." />
  const [head, ...fields] = component.fields
  const numeric = fields.find((field) => rows.every((row) => typeof row[field] === 'number'))
  const best = numeric ? Math.min(...rows.map((row) => Number(row[numeric]))) : null
  return (
    <div className="ta-table-wrap">
      <table className="ta-table ta-compare">
        <thead>
          <tr>
            <th scope="col">{label(head)}</th>
            {rows.map((row) => (
              <th key={String(row.id)} scope="col">
                {show(head, row[head])}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => (
            <tr key={field}>
              <th scope="row">{label(field)}</th>
              {rows.map((row) => (
                <td
                  key={String(row.id)}
                  className={
                    field === numeric && Number(row[field]) === best ? 'ta-best' : undefined
                  }
                >
                  {show(field, row[field])}
                  {field === numeric && Number(row[field]) === best ? ' (lowest)' : ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AlertPanel({ component, rows }: Props) {
  const field = component.group_by
  const alerts = field ? rows.filter((row) => tone(row[field]) !== 'good') : rows
  if (!alerts.length) return <Empty text="Nothing needs attention." />
  return (
    <ul className="ta-alerts">
      {alerts.map((row) => (
        <li
          key={String(row.id)}
          className={`ta-alert ta-alert--${field ? tone(row[field]) : 'wait'}`}
        >
          {field ? <Chip value={row[field]} /> : null}
          <span>{component.fields.map((item) => show(item, row[item])).join(' · ')}</span>
        </li>
      ))}
    </ul>
  )
}

function RecordForm({ component }: Props) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [message, setMessage] = useState('')
  const missing = component.fields.filter((field) => !values[field]?.trim())
  return (
    <form
      className="ta-form"
      onSubmit={(event) => {
        event.preventDefault()
        setMessage(
          missing.length
            ? `Fill in ${missing.map(label).join(', ')}.`
            : 'Checked. In the preview nothing is saved.',
        )
      }}
    >
      {component.fields.map((field) => (
        <label key={field}>
          <span>{label(field)}</span>
          <input
            value={values[field] ?? ''}
            onChange={(event) => setValues({ ...values, [field]: event.target.value })}
          />
        </label>
      ))}
      <button type="submit" className="ta-button">
        Save
      </button>
      {message ? (
        <p role="status" className="ta-form__message">
          {message}
        </p>
      ) : null}
    </form>
  )
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function ScheduleWeek({ component, rows }: Props) {
  const [person, day, start, end] = component.fields
  const people = [...new Set(rows.map((row) => String(row[person])))]
  if (!people.length) return <Empty text="No shifts planned this week." />
  return (
    <div className="ta-table-wrap">
      <table className="ta-table ta-schedule">
        <thead>
          <tr>
            <th scope="col">{label(person)}</th>
            {DAYS.map((name) => (
              <th key={name} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {people.map((name) => (
            <tr key={name}>
              <th scope="row">{name}</th>
              {DAYS.map((dayName) => {
                const shift = rows.find(
                  (row) => String(row[person]) === name && String(row[day]) === dayName,
                )
                return (
                  <td key={dayName}>
                    {shift ? (
                      <span className="ta-shift">{`${show(start, shift[start])}–${show(end, shift[end])}`}</span>
                    ) : null}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const RENDERERS = {
  filter_bar: FilterBar,
  metric_strip: MetricStrip,
  product_grid: ProductGrid,
  data_table: DataTable,
  detail_panel: DetailPanel,
  status_board: StatusBoard,
  timeline: Timeline,
  task_queue: TaskQueue,
  comparison_table: ComparisonTable,
  alert_panel: AlertPanel,
  record_form: RecordForm,
  schedule_week: ScheduleWeek,
} satisfies Record<TemplateComponent['type'], (props: Props) => ReactNode>

export function TemplateBlock(props: Props) {
  const Render = RENDERERS[props.component.type]
  return <Render {...props} />
}
