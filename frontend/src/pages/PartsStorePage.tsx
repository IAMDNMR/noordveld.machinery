import { SlidersHorizontal, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
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
    description: 'The right part for the machine. Search Noordveld parts by part number, description or machine, with fitment, specifications and availability from the Noordveld parts graph. Demonstration store.',
    path: STORE_ROUTE,
  })

  const [params, setParams] = useSearchParams()
  const query = parseQuery(params)
  const paramsKey = params.toString()
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
    <div className="wf-container store-page">
      <header className="store-hero">
        <p className="eyebrow">Parts Store</p>
        <h1 id="store-title">The right part for the machine.</h1>
        <p className="lede">Precisely identified. Clearly sourced. Search by part number, description or machine.</p>
        <div className="store-hero__search">
          <StoreSearch variant="hero" />
        </div>
        <p className="small muted">
          Prefer to describe what you need? <Link className="link-more" to="/agentic-shopping">Tell the agent</Link> · Need to understand fitment, suppliers or how parts connect?{' '}
          <Link className="link-more" to="/parts-intelligence">Ask Parts Intelligence</Link>
        </p>
      </header>

      <section id="results" className="store-layout" aria-labelledby="results-title">
        <aside className="store-filters" aria-label="Filters">
          <FilterPanel query={query} options={options} onChange={update} onClear={clear} />
        </aside>

        <div className="store-main">
          <div className="store-toolbar">
            <h2 id="results-title" className="store-count" aria-live="polite">
              {total === undefined ? 'Parts' : `${total} ${total === 1 ? 'part' : 'parts'}${query.category ? ` in ${query.category}` : ''}`}
            </h2>
            <div className="row">
              <button type="button" className="btn btn-secondary btn-sm store-filter-btn" onClick={() => setSheet(true)}>
                <SlidersHorizontal size={15} strokeWidth={1.8} aria-hidden="true" />
                Filters{active ? ` (${active})` : ''}
              </button>
              <label className="store-sort">
                <span className="sr-only">Sort by</span>
                <select value={query.sort} onChange={(e) => update({ sort: e.target.value as PartQuery['sort'] })}>
                  {SORTS.map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          {chips.length > 0 ? (
            <ul className="chip-row store-chips" aria-label="Active filters">
              {chips.map((c) => (
                <li key={c.key}>
                  <button type="button" className="chip" onClick={c.remove} aria-label={`Remove filter ${c.label}`}>
                    {c.label}
                    <X size={13} strokeWidth={2} aria-hidden="true" />
                  </button>
                </li>
              ))}
              {chips.length > 1 ? (
                <li>
                  <button type="button" className="link-more" onClick={resetAll}>
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
                <button type="button" className="btn btn-secondary" onClick={resetAll}>
                  Reset search and filters
                </button>
              }
            >
              Try a shorter search, a part number, or remove a filter.
            </EmptyView>
          ) : (
            <>
              <ul className="grid grid-3" aria-busy={parts.loading}>
                {parts.data.items.map((p) => (
                  <li key={p.part_id} className="store-cell">
                    <PartCard part={p} />
                  </li>
                ))}
              </ul>
              {pages > 1 ? (
                <nav className="store-pager" aria-label="Pages">
                  <button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => goToPage(page - 1)}>
                    Previous
                  </button>
                  <span className="small muted">
                    Page {page} of {pages}
                  </span>
                  <button type="button" className="btn btn-secondary btn-sm" disabled={page >= pages} onClick={() => goToPage(page + 1)}>
                    Next
                  </button>
                </nav>
              ) : null}
            </>
          )}

          <p className="disclaimer">Demonstration store. Part, fitment and legacy data come from the Noordveld parts graph; prices, stock and supply values are demonstration data and are labelled as such.</p>
        </div>
      </section>

      <div className={`sheet ${sheet ? 'is-open' : ''}`} aria-hidden={!sheet}>
        <button type="button" className="sheet__scrim" onClick={() => setSheet(false)} tabIndex={-1} aria-label="Close filters" />
        <div className="sheet__panel" role="dialog" aria-modal="true" aria-label="Filters" inert={!sheet}>
          <button type="button" className="sheet__close" onClick={() => setSheet(false)} aria-label="Close filters">
            <X size={22} strokeWidth={1.8} aria-hidden="true" />
          </button>
          <FilterPanel query={query} options={options} onChange={update} onClear={clear} />
          <button type="button" className="btn btn-primary btn-block sheet__apply" onClick={() => setSheet(false)}>
            {total === undefined ? 'Show parts' : `Show ${total} ${total === 1 ? 'part' : 'parts'}`}
          </button>
        </div>
      </div>
    </div>
  )
}
