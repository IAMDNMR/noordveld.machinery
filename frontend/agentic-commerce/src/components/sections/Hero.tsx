import { ButtonLink } from '../ui/ButtonLink'
import './hero.css'

export function Hero() {
  return (
    <section id="top" className="hero" aria-labelledby="hero-title">
      <div className="hero__content container">
        <h1 id="hero-title" className="display hero__title">
          From buying what you know <span className="hero__title-accent">to solving what you need.</span>
        </h1>
        <p className="lead hero__lead">Commerce is evolving from physical transactions, to digital discovery, to rapid fulfilment — and now to intelligent, outcome-oriented purchasing.</p>
        <div className="hero__actions">
          <ButtonLink href="#evolution">Explore the Evolution</ButtonLink>
          <ButtonLink href="#agentic" variant="secondary">
            See Agentic Commerce
          </ButtonLink>
        </div>
      </div>
    </section>
  )
}
