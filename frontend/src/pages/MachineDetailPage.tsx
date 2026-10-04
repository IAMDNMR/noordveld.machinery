import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ButtonLink } from '../components/ButtonLink'
import { FilmSlot } from '../components/media/FilmSlot'
import { MachineImage } from '../components/media/MachineImage'
import { Reveal } from '../components/Reveal'
import { company, films } from '../data/content'
import { useSite } from '../data/site'
import { useParallax } from '../hooks/useParallax'
import { usePageMeta } from '../hooks/usePageMeta'
import type { Machine } from '../types/catalog'
import NotFoundPage from './NotFoundPage'
import './pages.css'

const PREVIEW = 8

export default function MachineDetailPage() {
  const { model = '' } = useParams()
  const { data, error } = useSite()
  if (error) return <NotFoundPage />
  if (!data) {
    return (
      <section className="mhero" aria-busy="true">
        <div className="container mhero__inner">
          <p className="lead" role="status">
            Loading {model.toUpperCase()}…
          </p>
        </div>
      </section>
    )
  }
  const machine = data.machines.find((m) => m.slug === model.toLowerCase())
  return machine ? <MachineDetail machine={machine} machines={data.machines} /> : <NotFoundPage />
}

function MachineDetail({ machine, machines }: { machine: Machine; machines: readonly Machine[] }) {
  const imageRef = useRef<HTMLDivElement>(null)
  useParallax(imageRef, 40)
  const [showAll, setShowAll] = useState(false)

  usePageMeta({
    title: `${machine.model} ${machine.name}`,
    description: `${machine.description} ${machine.relatedParts.length} compatible parts in the catalogue.`,
    path: `/machines/${machine.slug}`,
  })

  const index = machines.findIndex((m) => m.model === machine.model)
  const prev = machines[(index - 1 + machines.length) % machines.length]
  const next = machines[(index + 1) % machines.length]

  const groups = useMemo(() => {
    const map = new Map<string, Machine['relatedParts'][number][]>()
    for (const p of machine.relatedParts) map.set(p.category, [...(map.get(p.category) ?? []), p])
    return Array.from(map, ([category, items]) => ({ category, items }))
  }, [machine])
  const visible = showAll ? machine.relatedParts : machine.relatedParts.slice(0, PREVIEW)
  const film = { ...films.machine, title: `${machine.model} at work` }

  return (
    <>
      <section className="mhero" aria-labelledby="machine-title">
        <div className="container mhero__inner">
          <div className="mhero__copy">
            <nav aria-label="Breadcrumb" className="crumbs">
              <Link to="/machines">Machines</Link>
              <span aria-hidden="true">/</span>
              <span aria-current="page">{machine.model}</span>
            </nav>
            <p className="mhero__model">{machine.model}</p>
            <h1 id="machine-title" className="hero-title mhero__name">
              {machine.name}
            </h1>
            <p className="lead">{machine.description}</p>
            <div className="mhero__actions">
              <ButtonLink to={`mailto:${company.email}?subject=${encodeURIComponent(`${machine.model} ${machine.name}`)}`} external>
                Contact Noordveld
              </ButtonLink>
              <a className="text-link" href="#related-parts">
                Explore parts
              </a>
            </div>
          </div>
          <div className="mhero__media" ref={imageRef}>
            <MachineImage machine={machine} ratio="4 / 3" eager imageType="studio" />
          </div>
        </div>
      </section>

      <section className="section detail" aria-labelledby="overview-title">
        <div className="container detail__grid">
          <Reveal>
            <h2 id="overview-title" className="h2">
              Overview
            </h2>
          </Reveal>
          <Reveal delay={100} className="detail__body">
            <p className="lead">
              {machine.model} is part of the {machine.brand === 'Noordveld' ? 'Noordveld' : `${machine.brand} (a Noordveld brand)`} range, in the {machine.family}, built at the {machine.plant} plant.
            </p>
            <ul className="facts-inline">
              <li>
                <span>Family</span>
                {machine.family}
              </li>
              <li>
                <span>Built at</span>
                {machine.plant}
              </li>
              <li>
                <span>Brand</span>
                {machine.brand}
                {machine.acquired ? `, acquired ${machine.acquired}` : ''}
              </li>
            </ul>
          </Reveal>
        </div>
      </section>

      <section className="section on-mist detail" aria-labelledby="specs-title">
        <div className="container detail__grid">
          <Reveal>
            <h2 id="specs-title" className="h2">
              Key specifications
            </h2>
          </Reveal>
          <Reveal delay={100} className="detail__body">
            <dl className="specs">
              {Object.entries(machine.specifications).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <p className="note">Detailed technical data is not part of the demonstration catalogue, so none is shown here.</p>
          </Reveal>
        </div>
      </section>

      <section className="section detail" aria-labelledby="application-title">
        <div className="container detail__grid">
          <Reveal>
            <h2 id="application-title" className="h2">
              Application
            </h2>
          </Reveal>
          <Reveal delay={100} className="detail__body">
            {machine.application ? (
              <>
                <p className="lead">
                  {machine.application.text}
                  {machine.application.context ? `, typically in ${machine.application.context.charAt(0).toLowerCase()}${machine.application.context.slice(1)}` : ''}.
                </p>
                <p className="note">Application profile: synthetic demo data in the Noordveld graph{machine.application.introduced ? `, introduced ${machine.application.introduced} (demo)` : ''}.</p>
              </>
            ) : (
              <p className="lead">No application profile is recorded for the {machine.model}.</p>
            )}
            {machine.attachments.length > 0 ? (
              <>
                <h3 className="detail__sub">Attachments in the catalogue</h3>
                <ul className="chips">
                  {machine.attachments.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </Reveal>
        </div>
      </section>

      <section id="related-parts" className="section on-mist detail" aria-labelledby="parts-title">
        <div className="container">
          <Reveal className="parts-head">
            <h2 id="parts-title" className="h2">
              Related parts
            </h2>
            <p className="lead">
              {machine.relatedParts.length === 0
                ? `No parts are catalogued for ${machine.model} in the demonstration data.`
                : `${machine.relatedParts.length} ${machine.relatedParts.length === 1 ? 'part is' : 'parts are'} catalogued for ${machine.model}${groups.length > 1 ? `, across ${groups.length} categories` : ''}.`}
            </p>
          </Reveal>
          {visible.length > 0 ? (
            <ul className="partlist">
              {visible.map((p) => (
                <li key={p.partNo} className="part">
                  <span className="part__no">{p.partNo}</span>
                  <span className="part__name">{p.name}</span>
                  <span className="part__cat">{p.category}</span>
                  <span className="part__spec">{p.specNote}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {machine.relatedParts.length > PREVIEW ? (
            <button type="button" className="text-link partlist__more" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
              {showAll ? 'Show fewer parts' : `Show all ${machine.relatedParts.length} parts`}
            </button>
          ) : null}
        </div>
      </section>

      <section className="section detail" aria-labelledby="film-title">
        <div className="container">
          <h2 id="film-title" className="sr-only">
            Film
          </h2>
          <Reveal>
            <FilmSlot film={film} ratio="21 / 9" />
          </Reveal>
        </div>
      </section>

      <section className="section on-dark mcta" aria-labelledby="mcta-title">
        <div className="container mcta__inner">
          <h2 id="mcta-title" className="h1">
            Talk to Noordveld about {machine.model}.
          </h2>
          <div className="mcta__actions">
            <ButtonLink to={`mailto:${company.email}?subject=${encodeURIComponent(machine.model)}`} external>
              Contact
            </ButtonLink>
            <ButtonLink to="/machines" variant="secondary" arrow={false}>
              Explore Machines
            </ButtonLink>
            <a className="text-link" href="#related-parts">
              Explore Parts
            </a>
          </div>
        </div>
        <div className="container siblings">
          <Link to={`/machines/${prev.slug}`} className="siblings__link">
            <ChevronLeft size={20} aria-hidden="true" />
            <span>
              <small>Previous</small>
              {prev.model} {prev.name}
            </span>
          </Link>
          <Link to={`/machines/${next.slug}`} className="siblings__link siblings__link--next">
            <span>
              <small>Next</small>
              {next.model} {next.name}
            </span>
            <ChevronRight size={20} aria-hidden="true" />
          </Link>
        </div>
      </section>
    </>
  )
}
