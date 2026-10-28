import { useEffect, useState } from 'react'
import { company } from '../data/content'
import { usePageMeta } from '../hooks/usePageMeta'
import { BusinessJourney } from '../components/process/BusinessJourney'
import {
  DealerLocator,
  IntelligenceMap,
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
import { useCatalogue } from '../sections/aftersales/data'
import '../sections/aftersales/aftersales.css'
import '../sections/aftersales/aftersales-redesign.css'

const SECTIONS = [
  ['aftersales-process', 'The business process'],
  ['find-parts', 'Your machine'],
  ['dealers', 'Dealer network'],
  ['service', 'Service'],
  ['tracking', 'Orders'],
] as const

/** The section nearest the top of the viewport, for the nav indicator. */
function useActiveSection() {
  const [active, setActive] = useState<string>('')
  useEffect(() => {
    const nodes = SECTIONS.map(([id]) => document.getElementById(id)).filter(
      (node): node is HTMLElement => node !== null,
    )
    if (!nodes.length || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) if (entry.isIntersecting) setActive(entry.target.id)
      },
      { rootMargin: '-35% 0px -55% 0px' },
    )
    nodes.forEach((node) => observer.observe(node))
    return () => observer.disconnect()
  }, [])
  return active
}

/**
 * After-sales Parts & Services: machine → component → part → compatibility → Parts Intelligence → ordering → delivery → dealer → service.
 * Every section is an entry into an existing capability (Parts Store, Parts Intelligence, Agentic Shopping, checkout, orders, Commerce Assistant); none re-implements one.
 */
export default function PartsServicesPage() {
  usePageMeta({
    title: 'Aftersales',
    description:
      'Find the right part, verify machine compatibility, explore recorded relationships and follow every order into service.',
    path: '/parts-services',
  })
  const active = useActiveSection()
  const catalogue = useCatalogue()
  const parts = catalogue.data?.parts ?? null
  const filters = catalogue.data?.filters ?? null
  return (
    <div className="as-page">
      <AftersalesHero />
      <nav className="as-section-nav" aria-label="Aftersales sections">
        <div className="container">
          <span>Parts &amp; service</span>
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`} aria-current={active === id ? 'true' : undefined}>
              {label}
            </a>
          ))}
          <a
            className="as-section-nav__cta"
            href={`mailto:${company.email}?subject=Aftersales%20support`}
          >
            Contact support
          </a>
        </div>
      </nav>
      <div id="aftersales-process" className="as-process-anchor">
        <BusinessJourney kind="aftersales" />
      </div>
      <PartSearch filters={filters} />
      <QuickAccess parts={parts} filters={filters} />
      <MachineFinder />
      <div className="container as-catalogue-browser">
        <details>
          <summary>Explore parts by category</summary>
          <Categories parts={parts} filters={filters} />
        </details>
        <details>
          <summary>Featured parts</summary>
          <FeaturedParts parts={parts} />
        </details>
      </div>
      <IntelligenceMap parts={parts} />
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
