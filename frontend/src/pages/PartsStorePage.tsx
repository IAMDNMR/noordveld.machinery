import { ArrowUpRight, Boxes, SlidersHorizontal, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getFilters, searchParts, type PartQuery } from '../api/index'
import { FilterPanel } from '../components/store/FilterPanel'
import { PartCard } from '../components/store/PartCard'
import { EmptyView, ErrorView, LoadingView } from '../components/store/StateViews'
import { StoreSearch } from '../components/store/StoreSearch'
import { OverviewVideoSlot } from '../components/media/OverviewVideoSlot'
import { ProcessFlow } from '../components/cine/Cine'
import { BusinessJourney } from '../components/process/BusinessJourney'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../hooks/usePageMeta'
import '../components/store/store-redesign.css'
import { humanize } from '../lib/format'
import {
  activeFilterCount,
  PAGE_SIZE,
  parseQuery,
  SORTS,
  STORE_ROUTE,
  toParams,
} from '../lib/storeQuery'

export default function PartsStorePage() {
  usePageMeta({
    title: 'Parts Portal',
    description:
      'The right part for the machine. Search Noordveld parts by part number, description or machine, with fitment, specifications and availability from the Noordveld parts graph. Demonstration store.',
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
  const update = (next: Partial<PartQuery>) =>
    setParams(toParams({ ...query, ...next }), { replace: true })
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
    ...(query.q.trim()
      ? [{ key: 'q', label: `“${query.q.trim()}”`, remove: () => update({ q: '' }) }]
      : []),
    ...(query.category
      ? [{ key: 'category', label: query.category, remove: () => update({ category: '' }) }]
      : []),
    ...(query.machine
      ? [{ key: 'machine', label: `Fits ${query.machine}`, remove: () => update({ machine: '' }) }]
      : []),
    ...query.availability.map((a) => ({
      key: a,
      label: humanize(a),
      remove: () => update({ availability: query.availability.filter((x) => x !== a) }),
    })),
    ...(query.orderable
      ? [
          {
            key: 'orderable',
            label: 'Orderable online',
            remove: () => update({ orderable: false }),
          },
        ]
      : []),
  ]

  return (
    <div className="wf-container store-page">
      <header className="store-hero">
        <div className="store-hero__main">
          <p className="eyebrow">Noordveld Parts Portal</p>
          <h1 id="store-title">
            The right part.
            <br />
            Ready for the next job.
          </h1>
          <p className="lede">
            Search the catalogue, check your machine’s fitment and review supply options in one
            place.
          </p>
          <div className="store-hero__search">
            <StoreSearch variant="hero" />
          </div>
          <p className="store-hero__hint">Search by part number, description or machine model.</p>
        </div>
        <div className="store-hero__media">
          <OverviewVideoSlot title="Parts Portal, explained" film="parts-portal" />
          <details className="store-hero__help">
            <summary>Help finding a part</summary>
            <aside className="store-assistance" aria-label="Help finding a part">
              <p className="eyebrow">A better way to find it</p>
              <Link to="/spark/chat">
                <Boxes size={22} strokeWidth={1.5} aria-hidden="true" />
                <span>
                  <strong>Describe what you need</strong>
                  <small>Compare suitable parts and supply options.</small>
                </span>
                <ArrowUpRight size={18} aria-hidden="true" />
              </Link>
              <p className="store-assistance__note">
                Demonstration catalogue · prices and stock are synthetic.
              </p>
            </aside>
          </details>
        </div>
      </header>

      {options?.categories.length ? (
        <nav className="store-category-rail" aria-label="Browse parts by category">
          <button
            type="button"
            aria-pressed={!query.category}
            onClick={() => update({ category: '' })}
          >
            All categories
          </button>
          {options.categories
            .filter((category) => category.part_count > 0)
            .map((category) => (
              <button
                key={category.category_id}
                type="button"
                aria-pressed={query.category === category.name}
                onClick={() => update({ category: category.name })}
              >
                {category.name}
                <span>{category.part_count}</span>
              </button>
            ))}
        </nav>
      ) : null}

      <section className="store-flow" aria-labelledby="store-flow-title">
        <h2 id="store-flow-title">From search to delivery</h2>
        <ProcessFlow
          label="How a parts order moves"
          steps={[
            {
              title: 'Search',
              text: 'By part number, description or machine model.',
              to: '#results',
            },
            { title: 'Check fitment', text: 'See which machines the part is recorded as fitting.' },
            { title: 'Compare supply', text: 'Depot stock, routes and delivery estimates.' },
            {
              title: 'Order',
              text: 'Check out here, or let Spark guide the order.',
              to: '/spark/chat',
            },
            { title: 'Track', text: 'Follow allocation, shipment and delivery.', to: '/orders' },
          ]}
        />
      </section>

      <details className="store-process">
        <summary>Who does what at each step</summary>
        <BusinessJourney kind="portal" />
      </details>
      <section id="results" className="store-layout" aria-labelledby="results-title">
        <aside className="store-filters" aria-label="Filters">
          <FilterPanel
            query={query}
            options={options}
            onChange={update}
            onClear={clear}
            showCategories={false}
          />
        </aside>

        <div className="store-main">
          <div className="store-toolbar">
            <h2 id="results-title" className="store-count" aria-live="polite">
              {parts.loading
                ? 'Finding parts…'
                : total === undefined
                  ? 'Parts'
                  : `${total} ${total === 1 ? 'part' : 'parts'}${query.category ? ` in ${query.category}` : ''}`}
            </h2>
            <div className="row">
              <button
                type="button"
                className="btn btn-secondary btn-sm store-filter-btn"
                onClick={() => setSheet(true)}
              >
                <SlidersHorizontal size={15} strokeWidth={1.8} aria-hidden="true" />
                Filters{active ? ` (${active})` : ''}
              </button>
              <label className="store-sort">
                <span className="sr-only">Sort by</span>
                <select
                  value={query.sort}
                  onChange={(e) => update({ sort: e.target.value as PartQuery['sort'] })}
                >
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
                  <button
                    type="button"
                    className="chip"
                    onClick={c.remove}
                    aria-label={`Remove filter ${c.label}`}
                  >
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
          ) : parts.loading || parts.data === null ? (
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
                    <PartCard part={p} machine={query.machine || null} />
                  </li>
                ))}
              </ul>
              {pages > 1 ? (
                <nav className="store-pager" aria-label="Pages">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={page <= 1}
                    onClick={() => goToPage(page - 1)}
                  >
                    Previous
                  </button>
                  <span className="small muted">
                    Page {page} of {pages}
                  </span>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={page >= pages}
                    onClick={() => goToPage(page + 1)}
                  >
                    Next
                  </button>
                </nav>
              ) : null}
            </>
          )}

          <p className="disclaimer">
            Demonstration store. Part, fitment and legacy data come from the Noordveld parts graph;
            prices, stock and supply values are demonstration data and are labelled as such.
          </p>
        </div>
      </section>

      <div className={`sheet ${sheet ? 'is-open' : ''}`} aria-hidden={!sheet}>
        <button
          type="button"
          className="sheet__scrim"
          onClick={() => setSheet(false)}
          tabIndex={-1}
          aria-label="Close filters"
        />
        <div
          className="sheet__panel"
          role="dialog"
          aria-modal="true"
          aria-label="Filters"
          inert={!sheet}
        >
          <button
            type="button"
            className="sheet__close"
            onClick={() => setSheet(false)}
            aria-label="Close filters"
          >
            <X size={22} strokeWidth={1.8} aria-hidden="true" />
          </button>
          <FilterPanel query={query} options={options} onChange={update} onClear={clear} />
          <button
            type="button"
            className="btn btn-primary btn-block sheet__apply"
            onClick={() => setSheet(false)}
          >
            {total === undefined ? 'Show parts' : `Show ${total} ${total === 1 ? 'part' : 'parts'}`}
          </button>
        </div>
      </div>
    </div>
  )
}
