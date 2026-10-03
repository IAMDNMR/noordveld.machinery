import { iconFor, availabilityMeta, fitModels, storeCategories } from '../../data/store'
import { activeFilterCount, applyFilters, PRICE_BANDS, type Filters } from '../../data/storeFilters'
import type { Availability } from '../../types/store'

interface FilterPanelProps {
  filters: Filters
  onChange: (next: Partial<Filters>) => void
  onClear: () => void
}

const AV: readonly Availability[] = ['IN_STOCK', 'LIMITED', 'BACKORDER']

/** Facet counts show what you would get if you picked an option, given every other filter. */
export function FilterPanel({ filters, onChange, onClear }: FilterPanelProps) {
  const catPool = applyFilters(filters, 'cat')
  const fitPool = applyFilters(filters, 'fit')
  const avPool = applyFilters(filters, 'av')
  const pricePool = applyFilters(filters, 'price')
  const orderPool = applyFilters(filters, 'orderable')
  const active = activeFilterCount(filters)

  return (
    <div className="filters">
      <div className="filters__head">
        <h2>Filters</h2>
        {active > 0 ? (
          <button type="button" onClick={onClear}>
            Clear all ({active})
          </button>
        ) : null}
      </div>

      <fieldset>
        <legend>Category</legend>
        <ul className="filters__cats">
          <li>
            <label className={!filters.cat ? 'is-on' : undefined}>
              <input type="radio" name="cat" checked={!filters.cat} onChange={() => onChange({ cat: '' })} />
              <span className="filters__label">All categories</span>
              <span className="filters__n">{catPool.length}</span>
            </label>
          </li>
          {storeCategories.map((c) => {
            const Icon = iconFor(c.name)
            const n = catPool.filter((p) => p.category === c.name).length
            return (
              <li key={c.id}>
                <label className={filters.cat === c.name ? 'is-on' : n === 0 ? 'is-empty' : undefined}>
                  <input type="radio" name="cat" checked={filters.cat === c.name} onChange={() => onChange({ cat: c.name })} />
                  <Icon size={17} strokeWidth={1.5} aria-hidden="true" />
                  <span className="filters__label">{c.name}</span>
                  <span className="filters__n">{n}</span>
                </label>
              </li>
            )
          })}
        </ul>
      </fieldset>

      <fieldset>
        <legend>Fits machine</legend>
        <div className="filters__select">
          <select value={filters.fit} onChange={(e) => onChange({ fit: e.target.value })} aria-label="Fits machine">
            <option value="">Any machine</option>
            {fitModels.map((m) => (
              <option key={m} value={m}>
                {m} ({fitPool.filter((p) => p.fits.includes(m)).length})
              </option>
            ))}
          </select>
        </div>
        <p className="filters__hint">Fitment is stated in the Noordveld catalogue.</p>
      </fieldset>

      <fieldset>
        <legend>Availability</legend>
        <ul className="filters__checks">
          {AV.map((a) => (
            <li key={a}>
              <label>
                <input type="checkbox" checked={filters.av.includes(a)} onChange={(e) => onChange({ av: e.target.checked ? [...filters.av, a] : filters.av.filter((x) => x !== a) })} />
                <span className={`filters__dot filters__dot--${availabilityMeta[a].tone}`} aria-hidden="true" />
                <span className="filters__label">{availabilityMeta[a].label}</span>
                <span className="filters__n">{avPool.filter((p) => p.availability === a).length}</span>
              </label>
            </li>
          ))}
        </ul>
      </fieldset>

      <fieldset>
        <legend>Price, excluding VAT</legend>
        <div className="filters__chips">
          {PRICE_BANDS.map((b) => (
            <button key={b.id} type="button" className={filters.price === b.id ? 'is-on' : undefined} aria-pressed={filters.price === b.id} onClick={() => onChange({ price: filters.price === b.id ? '' : b.id })}>
              {b.label}
              <span>{pricePool.filter((p) => b.test(p.price)).length}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <label className="filters__switch">
        <input type="checkbox" role="switch" checked={filters.orderable} onChange={(e) => onChange({ orderable: e.target.checked })} />
        <span className="filters__track" aria-hidden="true" />
        <span className="filters__label">
          Orderable online only
          <small>{orderPool.filter((p) => p.orderable).length} parts</small>
        </span>
      </label>
    </div>
  )
}
