import { ButtonLink } from '../components/ButtonLink'
import { FilmSlot } from '../components/media/FilmSlot'
import { Reveal } from '../components/Reveal'
import { AGENTIC_ROUTE, company, films } from '../data/content'

export function AgenticTeaser() {
  return (
    <section id="agentic" className="section on-dark teaser" aria-labelledby="teaser-title">
      <div className="container teaser__layout">
        <Reveal>
          <p className="label">The next generation of commerce</p>
          <h2 id="teaser-title" className="hero-title teaser__title">
            What if you didn’t have to know the part?
          </h2>
        </Reveal>
        <div className="teaser__side">
          <Reveal delay={120}>
            <p className="lead">Describe what you need. The next generation of commerce can help you find the right solution.</p>
          </Reveal>
          <Reveal delay={200}>
            <blockquote className="teaser__quote">
              <p>My machine is down. I need it operational quickly.</p>
            </blockquote>
          </Reveal>
          <Reveal delay={280}>
            <ButtonLink to={AGENTIC_ROUTE} external>
              Explore Agentic E-Commerce
            </ButtonLink>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

export function FinalCta() {
  return (
    <section className="section final" aria-labelledby="final-title">
      <div className="container">
        <Reveal className="final__film">
          <FilmSlot film={films.brand} />
        </Reveal>
        <div className="final__copy">
          <Reveal>
            <h2 id="final-title" className="h1">
              Let’s talk about the work ahead.
            </h2>
          </Reveal>
          <Reveal delay={120} className="final__actions">
            <ButtonLink to="/machines">Explore Machines</ButtonLink>
            <ButtonLink to={`mailto:${company.email}`} external variant="secondary" arrow={false}>
              Contact Noordveld
            </ButtonLink>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
