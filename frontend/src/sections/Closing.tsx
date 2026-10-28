import { ButtonLink } from '../components/ButtonLink'
import { company } from '../data/content'

export function FinalCta() {
  return (
    <section className="section final" aria-labelledby="final-title">
      <div className="container">
        <div className="final__copy">
          <div>
            <h2 id="final-title" className="h1">
              Let’s build
              <br />
              <em>what’s next.</em>
            </h2>
          </div>
          <div className="final__actions">
            <ButtonLink to="/machines">Explore Machines</ButtonLink>
            <ButtonLink to={`mailto:${company.email}`} external variant="secondary" arrow={false}>
              Contact Noordveld
            </ButtonLink>
          </div>
        </div>
      </div>
    </section>
  )
}
