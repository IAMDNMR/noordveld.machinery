import { useRef } from 'react'
import { ButtonLink } from '../components/ButtonLink'
import { FilmSlot } from '../components/media/FilmSlot'
import { films } from '../data/content'
import { useParallax } from '../hooks/useParallax'

export function Hero() {
  const filmRef = useRef<HTMLDivElement>(null)
  useParallax(filmRef, 60)
  return (
    <section className="hero on-dark" aria-labelledby="hero-title">
      <div className="hero__glow" aria-hidden="true" />
      <span className="hero__word" aria-hidden="true">
        {films.hero.word}
      </span>
      <div className="hero__film" ref={filmRef}>
        <FilmSlot film={films.hero} size="hero" />
      </div>
      <div className="hero__shade" aria-hidden="true" />
      <div className="hero__copy container">
        <p className="label hero__label">NOORDVELD MACHINERY B.V.</p>
        <h1 id="hero-title" className="hero-title">
          Built for demanding work.
        </h1>
        <p className="lead hero__lead">Industrial and agricultural machinery engineered for performance, reliability and the work that keeps industries moving.</p>
        <div className="hero__actions">
          <ButtonLink to="/machines">Explore Machines</ButtonLink>
          <ButtonLink to="/#company" variant="secondary" arrow={false}>
            Our Company
          </ButtonLink>
        </div>
      </div>
    </section>
  )
}
