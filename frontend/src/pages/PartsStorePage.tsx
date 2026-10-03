import { Cog, LayoutGrid, Rows3, SlidersHorizontal, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getFilters, searchParts, type PartQuery } from '../api'
import { FilterPanel } from '../components/store/FilterPanel'
import { PartCard } from '../components/store/PartCard'
import { EmptyView, ErrorView, LoadingView } from '../components/store/StateViews'
import { StoreSearch } from '../components/store/StoreSearch'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../hooks/usePageMeta'
import { humanize } from '../lib/format'
import { activeFilterCount, PAGE_SIZE, parseQuery, SORTS, STORE_ROUTE, toParams } from '../lib/storeQuery'

export default function PartsStorePage() {
  usePageMeta({
    title: 'Parts Store',
    description: 'Find the right Noordveld part for the work. Search by part name, part number, legacy reference or machine, with fitment, specifications and availability from the Noordveld parts graph. Demonstration store.',
    path: STORE_ROUTE,
  })

  const [params, setParams] = useSearchParams()
  const query = parseQuery(params)
  const paramsKey = params.toString()
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [sheet, setSheet] = useState(false)

  const parts = useApi((signal) => searchParts(query, signal), paramsKey)
  const filters = useApi((signal) => getFilters(signal), 'filters')
  const options = filters.data

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

  const page = Math.floor(query.offset / PAGE_SIZE) + 1
  const update = (next: Partial<PartQuery>) => setParams(toParams({ ...query, ...next }), { replace: true })
  const goToPage = (n: number) => {
    setParams(toParams({ ...query, page: n }))
    document.getElementById('results')?.scrollIntoView({ block: 'start' })
  }
  const clear = () => update({ category: '', machine: '', availability: [], orderable: false })
  const resetAll = () => setParams(new URLSearchParams(), { replace: true })
  const browse = (next: Partial<PartQuery>) => {
    update(next)
    requestAnimationFrame(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  const active = activeFilterCount(query)
  const total = parts.data?.total
  const pages = total === undefined ? 1 : Math.max(1, Math.ceil(total / PAGE_SIZE))
  const chips: { key: string; label: string; remove: () => void }[] = [
    ...(query.q.trim() ? [{ key: 'q', label: `“${query.q.trim()}”`, remove: () => update({ q: '' }) }] : []),
    ...(query.category ? [{ key: 'category', label: query.category, remove: () => update({ category: '' }) }] : []),
    ...(query.machine ? [{ key: 'machine', label: `Fits ${query.machine}`, remove: () => update({ machine: '' }) }] : []),
    ...query.availability.map((a) => ({ key: a, label: humanize(a), remove: () => update({ availability: query.availability.filter((x) => x !== a) }) })),
    ...(query.orderable ? [{ key: 'orderable', label: 'Orderable online', remove: () => update({ orderable: false }) }] : []),
  ]

  return (
    <>
      <section className="shero on-dark" aria-labelledby="store-title">
        <div className="shero__glow" aria-hidden="true" />
        <div className="container shero__inner">
          <p className="label shero__label">Agentic E-Commerce · Parts Store</p>
          <h1 id="store-title" className="hero-title shero__title">
            Find the right part for the work.
          </h1>
          <p className="lead shero__lead">Search by part name, part number, legacy reference or machine, or browse by machine and category.</p>
          <div className="shero__search">
            <StoreSearch variant="hero" />
          </div>
          {options ? (
            <>
              <ul className="shero__cats" aria-label="Browse by category">
                {options.categories.map((c) => (
                  <li key={c.category_id}>
                    <button type="button" onClick={() => browse({ category: c.name })}>
                      <Cog size={18} strokeWidth={1.5} aria-hidden="true" />
                      {c.name}
                      <span>{c.part_count}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <ul className="shero__cats shero__cats--machines" aria-label="Browse by machine">
                {options.machines.map((m) => (
                  <li key={m.machine_id}>
                    <button type="button" onClick={() => browse({ machine: m.model_code })}>
                      <span className="mono shero__model">{m.model_code}</span>
                      <span>{m.part_count}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      </section>

      <section id="results" className="scat container" aria-labelledby="results-title">
        <aside className="scat__side" aria-label="Filters">
          <FilterPanel query={query} options={options} onChange={update} onClear={clear} />
        </aside>

        <div className="scat__main">
          <div className="scat__bar">
            <h2 id="results-title" className="scat__count" aria-live="polite">
              {total === undefined ? (
                'Parts'
              ) : (
                <>
                  <strong>{total}</strong> {total === 1 ? 'part' : 'parts'}
                  {query.category ? <span> in {query.category}</span> : null}
                </>
              )}
            </h2>
            <div className="scat__tools">
              <button type="button" className="scat__filter-btn" onClick={() => setSheet(true)}>
                <SlidersHorizontal size={17} strokeWidth={1.8} aria-hidden="true" />
                Filters{active ? ` (${active})` : ''}
              </button>
              <label className="scat__sort">
                <span className="sr-only">Sort by</span>
                <select value={query.sort} onChange={(e) => update({ sort: e.target.value as PartQuery['sort'] })}>
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
                  <button type="button" className="scat__chips-clear" onClick={resetAll}>
                    Clear everything
                  </button>
                </li>
              ) : null}
            </ul>
          ) : null}

          {parts.error ? (
            <ErrorView error={parts.error} onRetry={parts.reload} what="The parts list" />
          ) : parts.data === null ? (
            <LoadingView label="Loading parts" />
          ) : parts.data.items.length === 0 ? (
            <EmptyView
              title="No parts match"
              action={
                <button type="button" className="button button--secondary" onClick={resetAll}>
                  Reset search and filters
                </button>
              }
            >
              Try a shorter search, a part number, or remove a filter.
            </EmptyView>
          ) : (
            <>
              <ul className={`scat__grid scat__grid--${view}`} aria-busy={parts.loading}>
                {parts.data.items.map((p) => (
                  <li key={p.part_id}>
                    <PartCard part={p} layout={view === 'list' ? 'row' : 'tile'} />
                  </li>
                ))}
              </ul>
              {pages > 1 ? (
                <nav className="scat__pager" aria-label="Pages">
                  <button type="button" className="button button--secondary" disabled={page <= 1} onClick={() => goToPage(page - 1)}>
                    Previous
                  </button>
                  <p>
                    Page {page} of {pages}
                  </p>
                  <button type="button" className="button button--secondary" disabled={page >= pages} onClick={() => goToPage(page + 1)}>
                    Next
                  </button>
                </nav>
              ) : null}
            </>
          )}

          <p className="scat__note">Demonstration store. Part, fitment and legacy data come from the Noordveld parts graph; prices, stock and supply values are demonstration data and are labelled as such.</p>
        </div>
      </section>

      <div className={`sheet ${sheet ? 'is-open' : ''}`} aria-hidden={!sheet}>
        <button type="button" className="sheet__scrim" onClick={() => setSheet(false)} tabIndex={-1} aria-label="Close filters" />
        <div className="sheet__panel" role="dialog" aria-modal="true" aria-label="Filters" inert={!sheet}>
          <button type="button" className="sheet__close" onClick={() => setSheet(false)} aria-label="Close filters">
            <X size={22} strokeWidth={1.8} aria-hidden="true" />
          </button>
          <FilterPanel query={query} options={options} onChange={update} onClear={clear} />
          <button type="button" className="button button--primary sheet__apply" onClick={() => setSheet(false)}>
            {total === undefined ? 'Show parts' : `Show ${total} ${total === 1 ? 'part' : 'parts'}`}
          </button>
        </div>
      </div>
    </>
  )
}
