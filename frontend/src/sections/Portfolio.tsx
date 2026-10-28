import { ChevronLeft, ChevronRight, ArrowUpRight } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { MachineImage } from '../components/media/MachineImage'
import { TextLink } from '../components/ButtonLink'
import { useSite } from '../data/site'

export function Portfolio() {
  const { data } = useSite()
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)
  const [family, setFamily] = useState<string | null>(null)
  const machines = useMemo(
    () => (data?.machines ?? []).filter((machine) => !family || machine.family === family),
    [data, family],
  )
  const featured =
    machines.find((machine) => machine.slug === selectedSlug) ??
    machines.find((machine) => machine.name === 'Wheel Loader' && machine.brand === 'Noordveld') ??
    machines[0] ??
    null
  const selectedIndex = featured ? machines.indexOf(featured) : -1
  const railRef = useRef<HTMLUListElement>(null)
  const [progress, setProgress] = useState(0)
  const [visibleIndex, setVisibleIndex] = useState(0)
  const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const update = useCallback(() => {
    const rail = railRef.current
    if (!rail) return
    const max = rail.scrollWidth - rail.clientWidth
    setProgress(max > 0 ? rail.scrollLeft / max : 0)
    const items = Array.from(rail.children) as HTMLElement[]
    const inset = parseFloat(getComputedStyle(rail).paddingLeft)
    const closest = items.reduce(
      (best, item, index) =>
        Math.abs(item.offsetLeft - rail.offsetLeft - inset - rail.scrollLeft) <
        Math.abs(items[best].offsetLeft - rail.offsetLeft - inset - rail.scrollLeft)
          ? index
          : best,
      0,
    )
    setVisibleIndex(closest)
  }, [])

  useEffect(() => {
    const rail = railRef.current
    const item = rail?.children[
      machines.findIndex((machine) => machine.slug === featured?.slug)
    ] as HTMLElement | undefined
    if (rail && item)
      rail.scrollTo({
        left: Math.max(
          0,
          item.offsetLeft - rail.offsetLeft - parseFloat(getComputedStyle(rail).paddingLeft),
        ),
        behavior: 'instant',
      })
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [featured, machines, update])

  const selectMachine = (slug: string, reveal = false) => {
    setSelectedSlug(slug)
    if (reveal)
      requestAnimationFrame(() => {
        document.getElementById('machine-preview-title')?.focus({ preventScroll: true })
        document
          .getElementById('machine-viewer')
          ?.scrollIntoView({ behavior: reduced() ? 'instant' : 'smooth', block: 'start' })
      })
  }
  const scrollBy = (direction: 1 | -1) => {
    const rail = railRef.current
    if (rail)
      rail.scrollBy({
        left: direction * rail.clientWidth * 0.7,
        behavior: reduced() ? 'instant' : 'smooth',
      })
  }

  return (
    <section id="machines" className="section portfolio" aria-labelledby="portfolio-title">
      <div className="container">
        <div className="portfolio__head">
          <div>
            <p className="label">01 / MACHINERY</p>
            <h2 id="portfolio-title" className="h1">
              Machines built to perform.
            </h2>
          </div>
          <div className="portfolio__intro">
            <p className="lead">
              A closer look at the range. Choose a series, explore a machine, and see where it is
              made.
            </p>
            <TextLink to="/machines">
              {data ? `View all ${data.machines.length} machines` : 'View all machines'}
            </TextLink>
          </div>
        </div>
        {data ? (
          <div className="machine-families" role="group" aria-label="Machine series">
            <button type="button" aria-pressed={!family} onClick={() => setFamily(null)}>
              Complete range
            </button>
            {data.families.map((name) => (
              <button
                key={name}
                type="button"
                aria-pressed={family === name}
                onClick={() => setFamily(name)}
              >
                {name}
              </button>
            ))}
          </div>
        ) : null}
        {featured ? (
          <article id="machine-viewer" className="product-theatre" aria-label="Selected machine">
            <header className="product-theatre__heading">
              <span className="label">
                {featured.family} / {String(selectedIndex + 1).padStart(2, '0')} OF{' '}
                {machines.length}
              </span>
              <div className="product-theatre__title">
                <h3 id="machine-preview-title" tabIndex={-1}>
                  <span className="product-theatre__model">{featured.model}</span>{' '}
                  <span className="product-theatre__name">{featured.name}</span>
                </h3>
                <div className="product-theatre__switcher">
                  <button
                    type="button"
                    aria-label="Show previous machine"
                    disabled={selectedIndex <= 0}
                    onClick={() => selectMachine(machines[selectedIndex - 1].slug)}
                  >
                    <ChevronLeft size={22} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    aria-label="Show next machine"
                    disabled={selectedIndex >= machines.length - 1}
                    onClick={() => selectMachine(machines[selectedIndex + 1].slug)}
                  >
                    <ChevronRight size={22} aria-hidden="true" />
                  </button>
                </div>
              </div>
            </header>
            <div className="product-theatre__canvas">
              <Link
                className="product-theatre__visual"
                to={`/machines/${featured.slug}`}
                aria-label={`Explore ${featured.model}, ${featured.name}`}
              >
                <div key={featured.slug} className="product-theatre__photograph">
                  <MachineImage machine={featured} ratio="16 / 9" imageType="action" />
                </div>
                <span className="product-theatre__explore">
                  Explore machine <ArrowUpRight size={20} aria-hidden="true" />
                </span>
              </Link>
              <div className="product-theatre__details">
                <p>{featured.description}</p>
                <dl>
                  <div>
                    <dt>Manufactured in</dt>
                    <dd>{featured.plant}</dd>
                  </div>
                  <div>
                    <dt>Catalogue parts</dt>
                    <dd>{featured.relatedParts.length}</dd>
                  </div>
                  <div>
                    <dt>Series</dt>
                    <dd>{featured.family}</dd>
                  </div>
                </dl>
              </div>
            </div>
            <p className="sr-only" role="status">
              {selectedSlug ? `${featured.model}, ${featured.name} selected` : ''}
            </p>
          </article>
        ) : null}
      </div>
      <div className="rail">
        <ul
          className="rail__track"
          ref={railRef}
          onScroll={update}
          aria-label="Choose a machine to preview"
        >
          {machines.map((machine) => (
            <li
              key={machine.slug}
              className={`rail__item ${featured?.slug === machine.slug ? 'is-selected' : ''}`}
            >
              <div className="gallery-machine">
                <button
                  className="gallery-machine__select"
                  type="button"
                  aria-label={`Preview ${machine.model}, ${machine.name}`}
                  aria-pressed={featured?.slug === machine.slug}
                  onClick={() => selectMachine(machine.slug, true)}
                >
                  <MachineImage machine={machine} ratio="4 / 3" />
                  <span className="gallery-machine__caption">
                    <strong>{machine.model}</strong>
                    <span>{machine.name}</span>
                  </span>
                </button>
                <Link className="gallery-machine__details" to={`/machines/${machine.slug}`}>
                  Machine details <ArrowUpRight size={15} aria-hidden="true" />
                </Link>
              </div>
            </li>
          ))}
        </ul>
        <div className="container rail__controls">
          <p className="rail__index">
            {machines.length ? String(visibleIndex + 1).padStart(2, '0') : '—'}{' '}
            <span>/ {machines.length || '—'}</span>
          </p>
          <div className="rail__progress" aria-hidden="true">
            <span style={{ transform: `scaleX(${0.08 + 0.92 * progress})` }} />
          </div>
          <div className="rail__buttons">
            <button
              type="button"
              onClick={() => scrollBy(-1)}
              aria-label="Previous machines"
              disabled={progress <= 0.001}
            >
              <ChevronLeft size={22} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => scrollBy(1)}
              aria-label="Next machines"
              disabled={!machines.length || progress >= 0.999}
            >
              <ChevronRight size={22} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
