import { ButtonLink } from '../../components/ButtonLink'
import { OverviewVideoSlot } from '../../components/media/OverviewVideoSlot'
import './hero-video.css'
import { StatStrip } from '../../components/cine/Cine'
import { apiGet } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import { editorialImageUrl } from '../../lib/assets'

export function AftersalesHero() {
  const kpis = useApi(
    (signal) =>
      apiGet<{ dealers: number; suppliers: number; parts: number; fitments: number }>(
        '/intelligence/kpis',
        {},
        signal,
      ),
    'as-hero-kpis',
  )
  return (
    <section className="as-hero as-hero--video on-dark" aria-labelledby="as-hero-title">
      <div className="as-hero__scene" aria-hidden="true">
        <img src={editorialImageUrl('service')} alt="" />
      </div>
      <div className="container as-hero__video-layout">
        <div className="as-hero__copy">
          <p className="label as-hero__eyebrow">After-sales · Parts &amp; Services</p>
          <h1 id="as-hero-title" className="as-hero__title">
            <span>Beyond the machine.</span> <span className="accent">A lifetime of support.</span>
          </h1>
          <p className="lead as-hero__lead">
            Connect dealers, parts and service around every machine. From the first handover to
            maintenance, warranty and replacement parts—keep your customers working.
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
      <div className="container as-hero__live">
        {kpis.data ? (
          <StatStrip
            stats={[
              { value: kpis.data.dealers, label: 'Dealers in the network' },
              { value: kpis.data.suppliers, label: 'Suppliers' },
              { value: kpis.data.parts, label: 'Parts on record' },
              { value: kpis.data.fitments, label: 'Recorded fitments' },
            ]}
          />
        ) : (
          <p className="as-hero__scope">One connected service journey</p>
        )}
      </div>
    </section>
  )
}
