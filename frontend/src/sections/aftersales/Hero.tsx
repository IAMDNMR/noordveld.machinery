import { ButtonLink } from '../../components/ButtonLink'
import { OverviewVideoSlot } from '../../components/media/OverviewVideoSlot'
import './hero-video.css'

export function AftersalesHero() {
  return (
    <section className="as-hero as-hero--video on-dark" aria-labelledby="as-hero-title">
      <div className="container as-hero__video-layout">
        <div className="as-hero__copy">
          <p className="label as-hero__eyebrow">After-sales · Parts &amp; Services</p>
          <h1 id="as-hero-title" className="as-hero__title">
            <span>Every Machine Has a Story.</span> <span className="accent">Keep It Moving.</span>
          </h1>
          <p className="lead as-hero__lead">
            Find the right parts, understand machine compatibility, explore technical relationships,
            and connect every order to the service journey.
          </p>
          <div className="as-hero__actions">
            <ButtonLink to="/parts-store">Explore Parts</ButtonLink>
            <ButtonLink to="#find-parts" variant="secondary" arrow={false} external>
              Find the Right Part
            </ButtonLink>
          </div>
        </div>
        <OverviewVideoSlot title="Aftersales, explained" film="aftersales" />
      </div>
    </section>
  )
}
