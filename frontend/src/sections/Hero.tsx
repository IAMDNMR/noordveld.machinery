import { ArrowDown } from 'lucide-react'
import { ButtonLink } from '../components/ButtonLink'
import { FilmSlot } from '../components/media/FilmSlot'
import { films } from '../data/content'
import { useSite } from '../data/site'
import { CountUp } from '../components/CountUp'

export function Hero() {
  const { data } = useSite()
  return (
    <section className="hero industrial-hero on-dark" aria-labelledby="hero-title">
      <div className="hero__film">
        <FilmSlot film={films.hero} size="hero" />
      </div>
      <div className="hero__foot container">
        <a href="#company">
          Discover Noordveld <ArrowDown size={16} aria-hidden="true" />
        </a>
        {data ? (
          <dl className="hero__facts">
            <div>
              <dt>machine models</dt>
              <dd>
                <CountUp value={data.machines.length} />
              </dd>
            </div>
            <div>
              <dt>plants</dt>
              <dd>
                <CountUp value={data.plants.length} />
              </dd>
            </div>
          </dl>
        ) : (
          <span>01 / NOORDVELD</span>
        )}
      </div>
      <div className="hero__shade" aria-hidden="true" />
      <div className="hero__copy container">
        <p className="label hero__label">NOORDVELD MACHINERY B.V.</p>
        <h1 id="hero-title" className="hero-title" aria-label="Built for demanding work.">
          <span className="hero__line">
            <span>Built for</span>
          </span>
          <span className="hero__line">
            <span>demanding work.</span>
          </span>
        </h1>
        <p className="lead hero__lead">
          Industrial and agricultural machinery. Different engineering traditions. One Noordveld.
        </p>
        <div className="hero__actions">
          <ButtonLink to="/machines">Explore Machines</ButtonLink>
          <ButtonLink to="/#company" variant="secondary" arrow={false}>
            Our company
          </ButtonLink>
        </div>
      </div>
    </section>
  )
}
