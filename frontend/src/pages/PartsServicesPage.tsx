import { usePageMeta } from '../hooks/usePageMeta'
import {
  DealerLocator,
  IntelligenceMap,
  OrderJourney,
  ServiceJourney,
  Tracking,
  Trust,
} from '../sections/aftersales/Connect'
import {
  Categories,
  FeaturedParts,
  MachineFinder,
  PartSearch,
  QuickAccess,
} from '../sections/aftersales/Discover'
import { AftersalesHero } from '../sections/aftersales/Hero'
import { AftersalesLandscape } from '../sections/aftersales/Landscape'
import { useCatalogue } from '../sections/aftersales/data'
import '../sections/aftersales/aftersales.css'

/**
 * After-sales Parts & Services: machine → component → part → compatibility → Parts Intelligence → ordering → delivery → dealer → service.
 * Every section is an entry into an existing capability (Parts Portal, Parts Intelligence, Agentic Shopping, checkout, orders, Commerce Assistant); none re-implements one.
 */
export default function PartsServicesPage() {
  usePageMeta({
    title: 'Aftersales | Noordveld Machinery',
    description:
      'Find the right part, verify machine compatibility, explore recorded relationships and follow every order into service.',
    path: '/aftersales',
  })
  const catalogue = useCatalogue()
  const parts = catalogue.data?.parts ?? null
  const filters = catalogue.data?.filters ?? null
  return (
    <div className="as-page">
      <AftersalesHero parts={parts} />
      <AftersalesLandscape />
      <QuickAccess parts={parts} filters={filters} />
      <PartSearch filters={filters} />
      <Categories parts={parts} filters={filters} />
      <MachineFinder />
      <IntelligenceMap parts={parts} />
      <FeaturedParts parts={parts} />
      <OrderJourney />
      <DealerLocator />
      <ServiceJourney />
      <Tracking />
      <Trust />
      {catalogue.error ? (
        <p className="container as-note as-note--bad" role="alert">
          The catalogue could not be loaded, so parts, categories and featured items are not shown.{' '}
          <button type="button" className="as-inline" onClick={catalogue.reload}>
            Try again
          </button>
        </p>
      ) : null}
    </div>
  )
}
