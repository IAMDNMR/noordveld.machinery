import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { MachineCard } from '../components/MachineCard'
import { MachineImage } from '../components/media/MachineImage'
import { Reveal } from '../components/Reveal'
import { TextLink } from '../components/ButtonLink'
import { machineBySlug, machines } from '../data/machines'

const featured = machineBySlug('nv-4500')

export function Portfolio() {
  const railRef = useRef<HTMLUListElement>(null)
  const [progress, setProgress] = useState(0)

  const update = useCallback(() => {
    const rail = railRef.current
    if (!rail) return
    const max = rail.scrollWidth - rail.clientWidth
    setProgress(max > 0 ? rail.scrollLeft / max : 0)
  }, [])

  useEffect(() => {
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [update])

  const scrollBy = (dir: 1 | -1) => {
    const rail = railRef.current
    if (!rail) return
    rail.scrollBy({ left: dir * rail.clientWidth * 0.8, behavior: 'smooth' })
  }

  return (
    <section id="machines" className="section portfolio" aria-labelledby="portfolio-title">
      <div className="container">
        <div className="portfolio__head">
          <Reveal>
            <h2 id="portfolio-title" className="h1">
              Machines built to work.
            </h2>
          </Reveal>
          <Reveal delay={120} className="portfolio__intro">
            <p className="lead">Explore the Noordveld range across material handling, loading, conveying and industrial applications.</p>
            <TextLink to="/machines">View all 15 machines</TextLink>
          </Reveal>
        </div>

        {featured ? (
          <Reveal className="featured">
            <Link className="featured__link" to={`/machines/${featured.slug}`} aria-label={`${featured.model}, ${featured.name}`}>
              <div className="featured__media">
                <MachineImage machine={featured} ratio="21 / 9" reveal eager imageType="action" />
              </div>
              <div className="featured__body">
                <p className="featured__tag">Featured</p>
                <p className="featured__model">{featured.model}</p>
                <h3 className="h2 featured__name">{featured.name}</h3>
                <p className="featured__text">{featured.description}</p>
                <span className="text-link">Explore {featured.model}</span>
              </div>
            </Link>
          </Reveal>
        ) : null}
      </div>

      <div className="rail">
        <ul className="rail__track" ref={railRef} onScroll={update} aria-label="All Noordveld machines">
          {machines.map((m, i) => (
            <li key={m.model} className="rail__item">
              <MachineCard machine={m} index={i} ratio="4 / 3" />
            </li>
          ))}
        </ul>
        <div className="container rail__controls">
          <div className="rail__progress" aria-hidden="true">
            <span style={{ transform: `scaleX(${0.08 + 0.92 * progress})` }} />
          </div>
          <div className="rail__buttons">
            <button type="button" onClick={() => scrollBy(-1)} aria-label="Previous machines">
              <ChevronLeft size={22} aria-hidden="true" />
            </button>
            <button type="button" onClick={() => scrollBy(1)} aria-label="Next machines">
              <ChevronRight size={22} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
