import { LayoutGrid, PackageSearch, Rows3, SlidersHorizontal, Truck, ShieldCheck, Warehouse, ScanSearch, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FilterPanel } from '../components/store/FilterPanel'
import { PartCard } from '../components/store/PartCard'
import { StoreSearch } from '../components/store/StoreSearch'
import { allParts, availabilityMeta, fitModels, iconFor, storeCategories, storeWarehouses, STORE_DISCLAIMER, STORE_ROUTE } from '../data/store'
import { activeFilterCount, applyFilters, parseFilters, PRICE_BANDS, SORTS, sortParts, toParams, type Filters, type SortKey } from '../data/storeFilters'
import { usePageMeta } from '../hooks/usePageMeta'

const PAGE = 24

const promises = [
  { icon: ScanSearch, title: 'Right part, first time', text: 'Fitment comes straight from the Noordveld catalogue, per machine model.' },
  { icon: Warehouse, title: 'Live stock view', text: `Availability across ${storeWarehouses.length} warehouses and the dealer network.` },
  { icon: Truck, title: 'Delivery you can plan', text: 'Standard and express rates by distance, shown before you order.' },
  { icon: ShieldCheck, title: 'Compliance on record', text: 'Standards and certificates listed on every part page.' },
] as const

export default function PartsStorePage() {
  usePageMeta({
    title: 'Parts Store',
    description: `Noordveld Parts Store: ${allParts.length} parts across ${storeCategories.length} categories, with fitment by machine, availability and delivery estimates. Demonstration store.`,
    path: STORE_ROUTE,
  })

  const [params, setParams] = useSearchParams()
  const filters = useMemo(() => parseFilters(params), [params])
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [shown, setShown] = useState(PAGE)
  const [sheet, setSheet] = useState(false)

  const results = useMemo(() => sortParts(applyFilters(filters), filters), [filters])
  const active = activeFilterCount(filters)

  useEffect(() => setShown(PAGE), [params])
  useEffect(() => {
    if (!sheet) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setSheet(false)
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [sheet])

  const update = (next: Partial<Filters>) => setParams(toParams({ ...filters, ...next }), { replace: true })
  const clear = () => setParams(toParams({ ...filters, cat: '', fit: '', av: [], orderable: false, price: '' }), { replace: true })
  const pickCategory = (cat: string) => {
    update({ cat })
    requestAnimationFrame(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  const chips: { key: string; label: string; remove: () => void }[] = [
    ...(filters.q.trim() ? [{ key: 'q', label: `“${filters.q.trim()}”`, remove: () => update({ q: '' }) }] : []),
    ...(filters.cat ? [{ key: 'cat', label: filters.cat, remove: () => update({ cat: '' }) }] : []),
    ...(filters.fit ? [{ key: 'fit', label: `Fits ${filters.fit}`, remove: () => update({ fit: '' }) }] : []),
    ...filters.av.map((a) => ({ key: a, label: availabilityMeta[a].label, remove: () => update({ av: filters.av.filter((x) => x !== a) }) })),
    ...(filters.price ? [{ key: 'price', label: PRICE_BANDS.find((b) => b.id === filters.price)?.label ?? '', remove: () => update({ price: '' }) }] : []),
    ...(filters.orderable ? [{ key: 'ord', label: 'Orderable online', remove: () => update({ orderable: false }) }] : []),
  ]

  return (
    <>
      <section className="shero on-dark" aria-labelledby="store-title">
        <div className="shero__glow" aria-hidden="true" />
        <div className="container shero__inner">
          <p className="label shero__label">Agentic E-Commerce · Parts Store</p>
          <h1 id="store-title" className="hero-title shero__title">
            The right part, found fast.
          </h1>
          <p className="lead shero__lead">
            {allParts.length} Noordveld parts across {storeCategories.length} categories for {fitModels.length} machine models. Search by name, number or machine, check what is in stock, and see delivery before you order.
          </p>
          <div className="shero__search">
            <StoreSearch variant="hero" />
          </div>
          <ul className="shero__cats" aria-label="Shop by category">
            {storeCategories.map((c) => {
              const Icon = iconFor(c.name)
              return (
                <li key={c.id}>
                  <button type="button" onClick={() => pickCategory(c.name)}>
                    <Icon size={18} strokeWidth={1.5} aria-hidden="true" />
                    {c.name}
                    <span>{c.count}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      </section>

      <section className="spromise" aria-label="Why order here">
        <ul className="container spromise__list">
          {promises.map((p) => (
            <li key={p.title}>
              <p.icon size={22} strokeWidth={1.4} aria-hidden="true" />
              <div>
                <h2>{p.title}</h2>
                <p>{p.text}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section id="results" className="scat container" aria-labelledby="results-title">
        <aside className="scat__side" aria-label="Filters">
          <FilterPanel filters={filters} onChange={update} onClear={clear} />
        </aside>

        <div className="scat__main">
          <div className="scat__bar">
            <h2 id="results-title" className="scat__count" aria-live="polite">
              <strong>{results.length}</strong> {results.length === 1 ? 'part' : 'parts'}
              {filters.cat ? <span> in {filters.cat}</span> : null}
            </h2>
            <div className="scat__tools">
              <button type="button" className="scat__filter-btn" onClick={() => setSheet(true)}>
                <SlidersHorizontal size={17} strokeWidth={1.8} aria-hidden="true" />
                Filters{active ? ` (${active})` : ''}
              </button>
              <label className="scat__sort">
                <span className="sr-only">Sort by</span>
                <select value={filters.sort} onChange={(e) => update({ sort: e.target.value as SortKey })}>
                  {SORTS.map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="scat__view" role="group" aria-label="Layout">
                <button type="button" aria-pressed={view === 'grid'} onClick={() => setView('grid')} aria-label="Grid view">
                  <LayoutGrid size={18} strokeWidth={1.7} aria-hidden="true" />
                </button>
                <button type="button" aria-pressed={view === 'list'} onClick={() => setView('list')} aria-label="List view">
                  <Rows3 size={18} strokeWidth={1.7} aria-hidden="true" />
                </button>
              </div>
            </div>
          </div>

          {chips.length > 0 ? (
            <ul className="scat__chips" aria-label="Active filters">
              {chips.map((c) => (
                <li key={c.key}>
                  <button type="button" onClick={c.remove} aria-label={`Remove filter ${c.label}`}>
                    {c.label}
                    <X size={14} strokeWidth={2} aria-hidden="true" />
                  </button>
                </li>
              ))}
              {chips.length > 1 ? (
                <li>
                  <button type="button" className="scat__chips-clear" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
                    Clear everything
                  </button>
                </li>
              ) : null}
            </ul>
          ) : null}

          {results.length === 0 ? (
            <div className="scat__empty">
              <PackageSearch size={44} strokeWidth={1.1} aria-hidden="true" />
              <h3>No parts match</h3>
              <p>Try a shorter search, a part number such as NVM-1010-HY, or remove a filter.</p>
              <button type="button" className="button button--secondary" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
                Reset search and filters
              </button>
            </div>
          ) : (
            <>
              <ul className={`scat__grid scat__grid--${view}`}>
                {results.slice(0, shown).map((p) => (
                  <li key={p.id}>
                    <PartCard part={p} layout={view === 'list' ? 'row' : 'tile'} />
                  </li>
                ))}
              </ul>
              {shown < results.length ? (
                <div className="scat__more">
                  <p>
                    Showing {shown} of {results.length}
                  </p>
                  <button type="button" className="button button--secondary" onClick={() => setShown((n) => n + PAGE)}>
                    Show {Math.min(PAGE, results.length - shown)} more
                  </button>
                </div>
              ) : null}
            </>
          )}

          <p className="scat__note">{STORE_DISCLAIMER}</p>
        </div>
      </section>

      <div className={`sheet ${sheet ? 'is-open' : ''}`} aria-hidden={!sheet}>
        <div className="sheet__scrim" onClick={() => setSheet(false)} />
        <div className="sheet__panel" role="dialog" aria-modal="true" aria-label="Filters" inert={!sheet}>
          <button type="button" className="sheet__close" onClick={() => setSheet(false)} aria-label="Close filters">
            <X size={22} strokeWidth={1.8} aria-hidden="true" />
          </button>
          <FilterPanel filters={filters} onChange={update} onClear={clear} />
          <button type="button" className="button button--primary sheet__apply" onClick={() => setSheet(false)}>
            Show {results.length} {results.length === 1 ? 'part' : 'parts'}
          </button>
        </div>
      </div>
    </>
  )
}
