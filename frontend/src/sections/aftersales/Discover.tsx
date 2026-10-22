import { ArrowRight, Search } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { searchParts, type CatalogueFilters, type PartSummary } from '../../api'
import { Reveal } from '../../components/Reveal'
import { getSiteOverview } from '../../api/site'
import { useApi } from '../../hooks/useApi'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { editorialImageUrl, machineImageUrl, partImageUrl } from '../../lib/assets'
import { categoryPath, machinePath, partPath, STORE_ROUTE } from '../../lib/storeQuery'
import { label, priceText, withImage } from './data'

/* ───────── Quick access: six real destinations ───────── */

export function QuickAccess({
  parts,
  filters,
}: {
  parts: PartSummary[] | null
  filters: CatalogueFilters | null
}) {
  const pics = withImage(parts ?? [])
  const pic = (i: number) => (pics[i] ? partImageUrl(pics[i].part_number) : undefined)
  const firstMachine = filters?.machines.find((m) => m.part_count > 0)
  const items = [
    {
      title: 'Parts Store',
      text: 'Browse parts and continue into the ordering workflow.',
      to: STORE_ROUTE,
      img: pic(0),
      kind: 'part',
    },
    {
      title: 'Parts Intelligence',
      text: 'Investigate relationships, machine fitment and the supply evidence that is recorded.',
      to: '/parts-intelligence',
      img: editorialImageUrl('engineering'),
      kind: 'photo',
    },
    {
      title: 'Parts Catalogue',
      text: `Every catalogue item${parts ? ` (${parts.length})` : ''}, A to Z, with its details.`,
      to: `${STORE_ROUTE}?sort=name`,
      img: pic(3),
      kind: 'part',
    },
    {
      title: 'Find Parts for Your Machine',
      text: 'Identify the machine and see the parts with a recorded fitment.',
      to: '#find-parts',
      anchor: true,
      img: firstMachine ? machineImageUrl(firstMachine.model_code.toLowerCase()) : undefined,
      kind: 'photo',
    },
    {
      title: 'Dealer Locator',
      text: 'Find dealers by country from the recorded dealer network.',
      to: '#dealers',
      anchor: true,
      img: editorialImageUrl('work-environment'),
      kind: 'photo',
    },
    {
      title: 'Service & Maintenance',
      text: 'Maintenance parts and the service steps that are supported today.',
      to: '#service',
      anchor: true,
      img: editorialImageUrl('service'),
      kind: 'photo',
    },
  ]
  return (
    <section className="section as-quick" aria-labelledby="as-quick-title">
      <div className="container">
        <Reveal>
          <p className="label">Quick access</p>
          <h2 id="as-quick-title" className="h1">
            Everything aftermarket in one place.
          </h2>
        </Reveal>
        <ul className="as-quick__grid">
          {items.map((it, i) => (
            <Reveal as="li" key={it.title} delay={i * 70} className={`as-tile as-tile--${it.kind}`}>
              {it.anchor ? (
                <a href={it.to} className="as-tile__link">
                  <TileBody {...it} />
                </a>
              ) : (
                <Link to={it.to} className="as-tile__link">
                  <TileBody {...it} />
                </Link>
              )}
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  )
}

function TileBody({ title, text, img }: { title: string; text: string; img?: string }) {
  return (
    <>
      <span className="as-tile__media">{img ? <img src={img} alt="" loading="lazy" /> : null}</span>
      <span className="as-tile__text">
        <strong>{title}</strong>
        <span>{text}</span>
        <em>
          Open <ArrowRight size={15} aria-hidden="true" />
        </em>
      </span>
    </>
  )
}

/* ───────── Search: the store's own search; questions go to Parts Intelligence ───────── */

const QUESTION = /^(which|what|where|who|how|does|do|is|are|can|why)\b|\?$/i

export function PartSearch({ filters }: { filters: CatalogueFilters | null }) {
  const [text, setText] = useState('')
  const navigate = useNavigate()
  const q = useDebouncedValue(text.trim(), 280)
  const isQuestion = QUESTION.test(q)
  const live = useApi(
    (signal) =>
      q.length >= 2 && !isQuestion
        ? searchParts(
            {
              q,
              category: '',
              machine: '',
              availability: [],
              orderable: false,
              sort: 'relevance',
              offset: 0,
              limit: 6,
            },
            signal,
          )
        : Promise.resolve(null),
    `as-search:${q}`,
  )
  const machineHit = useMemo(() => {
    const low = q.toLowerCase().replace(/[\s_-]/g, '')
    return low.length >= 3
      ? filters?.machines.find((m) =>
          low.includes(m.model_code.toLowerCase().replace(/[\s_-]/g, '')),
        )
      : undefined
  }, [q, filters])
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const v = text.trim()
    if (!v) return
    navigate(
      QUESTION.test(v)
        ? `/parts-intelligence?${new URLSearchParams({ q: v })}`
        : `${STORE_ROUTE}?${new URLSearchParams({ q: v })}`,
    )
  }
  const results = live.data?.items ?? []
  return (
    <section className="section on-mist as-search" aria-labelledby="as-search-title">
      <div className="container as-search__inner">
        <Reveal>
          <p className="label">Intelligent parts search</p>
          <h2 id="as-search-title" className="h1">
            Find the Part. Verify the Fit. Get Moving.
          </h2>
          <p className="lead">
            Search by part number, part name, machine model or a description of the component. Ask a
            question and it goes to Parts Intelligence.
          </p>
        </Reveal>
        <form className="as-search__form" role="search" onSubmit={submit}>
          <label className="as-sr" htmlFor="as-search-input">
            Search parts
          </label>
          <Search size={22} aria-hidden="true" className="as-search__icon" />
          <input
            id="as-search-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Part number, part name, machine model or component"
            autoComplete="off"
          />
          <button type="submit" className="button button--primary">
            Search
          </button>
        </form>
        <div className="as-search__results" aria-live="polite">
          {isQuestion && q ? (
            <p className="as-note">
              That reads as a question:{' '}
              <button
                type="button"
                className="as-inline"
                onClick={() => navigate(`/parts-intelligence?${new URLSearchParams({ q })}`)}
              >
                ask Parts Intelligence
              </button>
              , which answers from the recorded relationships.
            </p>
          ) : null}
          {machineHit ? (
            <p className="as-note">
              <strong>{machineHit.model_code}</strong> is a machine in the catalogue (
              {machineHit.name}).{' '}
              {machineHit.part_count > 0 ? (
                <Link to={machinePath(machineHit.model_code)}>
                  See its {machineHit.part_count} parts with a recorded fitment →
                </Link>
              ) : (
                'No part has a recorded fitment for it yet.'
              )}
            </p>
          ) : null}
          {!isQuestion && q.length >= 2 && live.loading ? (
            <p className="as-note">Searching the catalogue…</p>
          ) : null}
          {live.error ? (
            <p className="as-note as-note--bad">The catalogue could not be searched right now.</p>
          ) : null}
          {!isQuestion && q.length >= 2 && !live.loading && live.data && results.length === 0 ? (
            <p className="as-note">
              No catalogue part matches “{q}”. Check the spelling or the part number, or{' '}
              <Link to={`/agentic-shopping?${new URLSearchParams({ q })}`}>
                describe the problem in Agentic E-Commerce
              </Link>
              . Nothing is suggested without a match.
            </p>
          ) : null}
          {results.length > 0 ? (
            <ul className="as-hits">
              {results.map((p) => (
                <li key={p.part_id}>
                  <Link to={partPath(p.part_number)}>
                    <span className="as-hits__img">
                      {partImageUrl(p.part_number) ? (
                        <img src={partImageUrl(p.part_number)} alt="" loading="lazy" />
                      ) : null}
                    </span>
                    <span>
                      <span className="as-mono">{p.part_number}</span>
                      <strong>{p.name}</strong>
                      <small>
                        {p.category}
                        {p.fitment.length
                          ? ` · fits ${p.fitment.map((f) => f.model_code).join(', ')}`
                          : ' · no recorded fitment'}
                      </small>
                    </span>
                  </Link>
                </li>
              ))}
              {live.data && live.data.total > results.length ? (
                <li className="as-hits__more">
                  <Link to={`${STORE_ROUTE}?${new URLSearchParams({ q })}`}>
                    All {live.data.total} results in the Parts Store →
                  </Link>
                </li>
              ) : null}
            </ul>
          ) : null}
        </div>
      </div>
    </section>
  )
}

/* ───────── Categories: only the categories the catalogue holds ───────── */

export function Categories({
  parts,
  filters,
}: {
  parts: PartSummary[] | null
  filters: CatalogueFilters | null
}) {
  const cats = (filters?.categories ?? []).filter((c) => c.part_count > 0)
  return (
    <section className="section as-cats" aria-labelledby="as-cats-title">
      <div className="container">
        <Reveal>
          <p className="label">Explore parts by category</p>
          <h2 id="as-cats-title" className="h1">
            Every system of the machine.
          </h2>
          <p className="lead">
            The categories below are the ones the catalogue holds. A category listing shows what is
            catalogued, not what is in stock.
          </p>
        </Reveal>
        {!filters ? <p className="as-note">Loading the catalogue…</p> : null}
        <ul className="as-cats__grid">
          {cats.map((c, i) => {
            const inCat = (parts ?? []).filter((p) => p.category === c.name)
            const img = withImage(inCat)[0]
            const subs = [...new Set(inCat.map((p) => p.subcategory).filter(Boolean))].slice(0, 3)
            return (
              <Reveal as="li" key={c.category_id} delay={(i % 5) * 60} className="as-cat">
                <Link to={categoryPath(c.name)}>
                  <span className="as-cat__media">
                    {img ? <img src={partImageUrl(img.part_number)} alt="" loading="lazy" /> : null}
                  </span>
                  <span className="as-cat__n">{String(i + 1).padStart(2, '0')}</span>
                  <strong>{c.name}</strong>
                  <span className="as-cat__sub">{subs.join(' · ')}</span>
                  <em>{c.part_count} catalogued</em>
                </Link>
              </Reveal>
            )
          })}
        </ul>
      </div>
    </section>
  )
}

/* ───────── Find parts for your machine: brand and model are the identification the data supports ───────── */

export function MachineFinder() {
  const site = useApi((s) => getSiteOverview(s), 'as-site')
  const machines = site.data?.machines ?? []
  const brands = [...new Set(machines.map((m) => m.brand).filter(Boolean))] as string[]
  const [brand, setBrand] = useState('')
  const [model, setModel] = useState('')
  const pool = machines.filter((m) => !brand || m.brand === brand)
  const machine = machines.find((m) => m.model === model)
  const fits = useApi(
    (signal) =>
      model
        ? searchParts(
            {
              q: '',
              category: '',
              machine: model,
              availability: [],
              orderable: false,
              sort: 'relevance',
              offset: 0,
              limit: 8,
            },
            signal,
          )
        : Promise.resolve(null),
    `as-fit:${model}`,
  )
  const img = machine ? machineImageUrl(machine.slug) : undefined
  return (
    <section
      id="find-parts"
      className="section on-dark as-finder"
      aria-labelledby="as-finder-title"
    >
      <div className="container as-finder__layout">
        <div className="as-finder__copy">
          <Reveal>
            <p className="label">Find parts for your machine</p>
            <h2 id="as-finder-title" className="h1">
              Start with the machine.
            </h2>
            <p className="lead">
              Choose the manufacturer and model. Only parts with a recorded fitment for that model
              are listed; nothing is inferred from a name.
            </p>
          </Reveal>
          <form className="as-finder__form" onSubmit={(e) => e.preventDefault()}>
            <label>
              <span>Manufacturer</span>
              <select
                value={brand}
                onChange={(e) => {
                  setBrand(e.target.value)
                  setModel('')
                }}
              >
                <option value="">All manufacturers</option>
                {brands.map((b) => (
                  <option key={b}>{b}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Machine model</span>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={!machines.length}
              >
                <option value="">{site.loading ? 'Loading machines…' : 'Choose a model'}</option>
                {pool.map((m) => (
                  <option key={m.model} value={m.model}>
                    {m.model} · {m.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="as-finder__hint">
              Serial-number and configuration lookup are not available: the catalogue identifies
              machines by model.
            </p>
          </form>
        </div>
        <div className="as-finder__result" aria-live="polite">
          <div className="as-finder__media">
            {img ? (
              <img src={img} alt={machine?.full_name ?? ''} loading="lazy" />
            ) : (
              <span className="as-finder__empty">
                {machine ? 'No photo of this machine' : 'Choose a machine model'}
              </span>
            )}
          </div>
          {model && fits.loading ? <p className="as-note">Reading the recorded fitment…</p> : null}
          {fits.error ? (
            <p className="as-note as-note--bad">The fitment could not be read right now.</p>
          ) : null}
          {model && fits.data && fits.data.total === 0 ? (
            <p className="as-note">
              No part has a recorded fitment for {model}. Ask Parts Intelligence or describe the
              problem in Agentic E-Commerce rather than guessing.
            </p>
          ) : null}
          {fits.data && fits.data.items.length > 0 ? (
            <>
              <ul className="as-fits">
                {fits.data.items.map((p) => {
                  const f = p.fitment.find((x) => x.model_code === model)
                  return (
                    <li key={p.part_id}>
                      <Link to={partPath(p.part_number)}>
                        <span className="as-mono">{p.part_number}</span>
                        <strong>{p.name}</strong>
                        <small>
                          {p.category} · fitment {label(f?.fitment_status)}
                        </small>
                      </Link>
                    </li>
                  )
                })}
              </ul>
              <Link className="as-finder__all" to={machinePath(model)}>
                All {fits.data.total} parts for {model} in the Parts Store →
              </Link>
            </>
          ) : null}
        </div>
      </div>
    </section>
  )
}

/* ───────── Featured parts: real catalogue entries with photos ───────── */

export function FeaturedParts({ parts }: { parts: PartSummary[] | null }) {
  const seen = new Set<string>()
  const pick = withImage(parts ?? [])
    .filter((p) => p.category && !seen.has(p.category) && seen.add(p.category))
    .slice(0, 8)
  return (
    <section className="section on-mist as-featured" aria-labelledby="as-featured-title">
      <div className="container">
        <Reveal>
          <p className="label">Featured parts</p>
          <h2 id="as-featured-title" className="h1">
            Precision you can identify.
          </h2>
          <p className="lead">
            One part from each system, straight from the catalogue. Prices and availability are
            shown only where they are recorded, and labelled as demonstration data.
          </p>
        </Reveal>
        <ul className="as-featured__grid">
          {pick.map((p, i) => (
            <Reveal as="li" key={p.part_id} delay={(i % 4) * 70} className="as-pcard">
              <div className="as-pcard__media">
                <img src={partImageUrl(p.part_number)} alt={p.name} loading="lazy" />
              </div>
              <div className="as-pcard__body">
                <span className="as-mono">{p.part_number}</span>
                <strong>{p.name}</strong>
                <small>{p.category}</small>
                <small>
                  {p.fitment.length
                    ? `Fits ${p.fitment.map((f) => f.model_code).join(', ')}`
                    : 'No recorded fitment'}
                </small>
                {priceText(p) ? (
                  <small className="as-pcard__price">
                    {priceText(p)}
                    {p.availability?.state ? ` · ${label(p.availability.state)}` : ''}
                  </small>
                ) : null}
                <span className="as-pcard__actions">
                  <Link to={partPath(p.part_number)} className="button button--primary">
                    View Details
                  </Link>
                  <Link
                    to={`${STORE_ROUTE}?${new URLSearchParams({ q: p.part_number })}`}
                    className="as-inline-link"
                  >
                    Find in Parts Store
                  </Link>
                </span>
              </div>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  )
}
