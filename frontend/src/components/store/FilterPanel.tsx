import type { CatalogueFilters, PartQuery } from '../../api'
import { humanize } from '../../lib/format'
import { activeFilterCount } from '../../lib/storeQuery'

interface FilterPanelProps {
  query: PartQuery
  /** Options come from /catalogue/filters; null while they load or if that call failed */
  options: CatalogueFilters | null
  onChange: (next: Partial<PartQuery>) => void
  onClear: () => void
}

export function FilterPanel({ query, options, onChange, onClear }: FilterPanelProps) {
  const active = activeFilterCount(query)
  const toggleAvailability = (state: string) =>
    onChange({ availability: query.availability.includes(state) ? query.availability.filter((s) => s !== state) : [...query.availability, state] })

  return (
    <form className="filters" onSubmit={(e) => e.preventDefault()} aria-label="Filter parts">
      <div className="filters__head">
        <h2>Filters</h2>
        {active > 0 ? (
          <button type="button" onClick={onClear}>
            Clear all
          </button>
        ) : null}
      </div>

      {options === null ? (
        <p className="filters__hint">Filter options are not available right now.</p>
      ) : (
        <>
          <fieldset className="filters__cats">
            <legend>Category</legend>
            {options.categories.map((c) => (
              <label key={c.category_id} className={`${query.category === c.name ? 'is-on' : ''} ${c.part_count === 0 ? 'is-empty' : ''}`}>
                <input type="radio" name="category" checked={query.category === c.name} onChange={() => onChange({ category: c.name })} onClick={() => query.category === c.name && onChange({ category: '' })} />
                <span className="filters__label">{c.name}</span>
                <span className="filters__n">{c.part_count}</span>
              </label>
            ))}
          </fieldset>

          <fieldset className="filters__select">
            <legend>Machine</legend>
            <label>
              <span className="sr-only">Fits machine</span>
              <select value={query.machine} onChange={(e) => onChange({ machine: e.target.value })}>
                <option value="">All machines</option>
                {options.machines.map((m) => (
                  <option key={m.machine_id} value={m.model_code}>
                    {m.model_code} · {m.part_count} parts
                  </option>
                ))}
              </select>
            </label>
            <p className="filters__hint">Parts with a recorded fitment for the model.</p>
          </fieldset>

          {options.availability.length > 0 ? (
            <fieldset className="filters__checks">
              <legend>Availability</legend>
              {options.availability.map((a) => (
                <label key={a.state}>
                  <input type="checkbox" checked={query.availability.includes(a.state)} onChange={() => toggleAvailability(a.state)} />
                  <span className="filters__label">{humanize(a.state)}</span>
                  <span className="filters__n">{a.part_count}</span>
                </label>
              ))}
            </fieldset>
          ) : null}
        </>
      )}

      <fieldset>
        <legend>Ordering</legend>
        <label className="filters__switch">
          <input type="checkbox" checked={query.orderable} onChange={(e) => onChange({ orderable: e.target.checked })} />
          <span className="filters__track" aria-hidden="true" />
          <span className="filters__label">Orderable online</span>
        </label>
      </fieldset>
    </form>
  )
}
