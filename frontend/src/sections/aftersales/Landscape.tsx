import { ArrowDown, ArrowRight, Boxes, Building2, Database, Network } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Reveal } from '../../components/Reveal'

const capabilities = [
  {
    title: 'Find the right part',
    detail: 'Catalogue, machine fitment and recorded part relationships.',
    to: '/parts-intelligence',
    action: 'Explore Parts Intelligence',
  },
  {
    title: 'Order and follow delivery',
    detail: 'Parts selection, checkout and your order history.',
    to: '/parts-store',
    action: 'Open Parts Portal',
  },
  {
    title: 'Find dealer and service information',
    detail: 'Dealer records and maintenance parts, with service availability shown below.',
    to: '#dealers',
    action: 'Find a dealer',
  },
]

export function AftersalesLandscape() {
  return (
    <section className="section as-landscape" aria-labelledby="as-landscape-title">
      <div className="container">
        <Reveal className="as-landscape__heading">
          <p className="label">The OEM–dealer connection</p>
          <h2 id="as-landscape-title" className="h1">
            One machine. A connected aftersales journey.
          </h2>
          <p className="body-lg">
            Aftersales brings parts discovery, ordering and dealer information together. It sits
            alongside the other services an OEM provides to its dealer network.
          </p>
        </Reveal>

        <div className="as-landscape__grid">
          <article className="as-landscape__current">
            <div className="as-landscape__caption">
              <Boxes size={20} aria-hidden="true" />
              <span>Our Aftersales offering</span>
              <span className="as-landscape__badge">Explore today</span>
            </div>
            <ul className="as-landscape__capabilities">
              {capabilities.map((item) => (
                <li key={item.title}>
                  <h3>{item.title}</h3>
                  <p>{item.detail}</p>
                  {item.to.startsWith('#') ? (
                    <a href={item.to}>
                      {item.action}
                      <ArrowRight size={16} aria-hidden="true" />
                    </a>
                  ) : (
                    <Link to={item.to}>
                      {item.action}
                      <ArrowRight size={16} aria-hidden="true" />
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </article>

          <aside className="as-landscape__context" aria-labelledby="as-oem-landscape-title">
            <div className="as-landscape__caption">
              <Building2 size={20} aria-hidden="true" />
              <span>The wider OEM landscape</span>
            </div>
            <h3 id="as-oem-landscape-title">
              A portal connects the services. Each module has its own job.
            </h3>
            <p>
              Machine configuration and sales, warranty claims, technical documents, telematics,
              dealer performance and training are separate parts of that landscape.
            </p>
            <details>
              <summary>
                Where dealer onboarding fits
                <ArrowDown size={16} aria-hidden="true" />
              </summary>
              <p>
                Onboarding establishes the dealer account, access rights and operating locations.
                Connecting the dealer’s own system then reduces duplicate entry and keeps shared
                records consistent.
              </p>
            </details>
          </aside>
        </div>

        <div className="as-dealer-flow" aria-labelledby="as-dealer-flow-title">
          <div className="as-dealer-flow__intro">
            <Network size={23} aria-hidden="true" />
            <div>
              <p className="label">Integration roadmap</p>
              <h3 id="as-dealer-flow-title">
                The dealer keeps its systems. Shared data connects the network.
              </h3>
            </div>
          </div>
          <ol className="as-dealer-flow__path">
            <li>
              <Building2 size={22} aria-hidden="true" />
              <div>
                <strong>Dealer systems</strong>
                <span>Sales, workshop, inventory, finance and CRM</span>
              </div>
            </li>
            <li>
              <Database size={22} aria-hidden="true" />
              <div>
                <strong>Agreed data interfaces</strong>
                <span>Customer and machine records, stock, orders, service history and claims</span>
              </div>
            </li>
            <li>
              <Network size={22} aria-hidden="true" />
              <div>
                <strong>OEM services</strong>
                <span>Consistent records across the dealer network</span>
              </div>
            </li>
          </ol>
        </div>
      </div>
    </section>
  )
}
