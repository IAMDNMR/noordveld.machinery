import { PackageSearch, Truck, Wrench, Tractor } from 'lucide-react'

// Set this to the supplied public video path when the overview film is ready.
const overviewFilm: string | null = null

export function AftersalesOverviewFilm() {
  return (
    <section className="as-overview-film" aria-labelledby="as-film-title">
      <div className="container as-overview-film__layout">
        <header>
          <p className="label">The complete journey</p>
          <h2 id="as-film-title">
            From a machine in the field
            <br />
            to the support behind it.
          </h2>
          <p>See how parts, knowledge, ordering and dealer support come together.</p>
          <a href="#aftersales-landscape">
            Explore how it connects <span aria-hidden="true">↓</span>
          </a>
        </header>
        {overviewFilm ? (
          // oxlint-disable-next-line jsx-a11y/media-has-caption -- Caption asset must accompany the supplied film.
          <video
            src={overviewFilm}
            controls
            playsInline
            preload="metadata"
            aria-label="The Noordveld aftersales journey"
          >
            Your browser cannot play this video.
          </video>
        ) : (
          <div
            className="as-overview-film__placeholder"
            aria-label="Space reserved for the aftersales overview film"
          >
            <div className="as-film-path">
              {[
                { icon: Tractor, label: 'Machine' },
                { icon: PackageSearch, label: 'Parts' },
                { icon: Truck, label: 'Delivery' },
                { icon: Wrench, label: 'Service' },
              ].map(({ icon: Icon, label }) => (
                <div key={label}>
                  <span>
                    <Icon size={24} strokeWidth={1.4} aria-hidden="true" />
                  </span>
                  <small>{label}</small>
                </div>
              ))}
            </div>
            <p>One connected aftersales journey.</p>
            <span className="as-film-status">Overview film · coming soon</span>
          </div>
        )}
      </div>
    </section>
  )
}
