import {
  ArrowRight,
  Building2,
  Database,
  Network,
  PackageSearch,
  ScanLine,
  Route,
  FileText,
  ShieldCheck,
  Radio,
  GraduationCap,
  ChartNoAxesCombined,
  Settings2,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import './aftersales-premium.css'

const offerings = [
  {
    name: 'Parts Portal',
    icon: PackageSearch,
    detail: 'Find the right component, check recorded fitment and review a parts order.',
    to: '/parts-store',
    action: 'Explore parts',
  },
  {
    name: 'Spark · Parts Intelligence',
    icon: ScanLine,
    detail: 'Ask a question and follow the relationships behind the answer.',
    to: '/spark/chat',
    action: 'Ask Spark',
  },
  {
    name: 'Agentic Shopping',
    icon: Route,
    detail: 'Describe a need. Compare suitable parts, availability and delivery options.',
    to: '/spark/chat',
    action: 'Describe your need',
  },
]
const modules = [
  {
    name: 'Dealer portal',
    icon: Network,
    detail: 'A shared entry point for orders, claims, documents and announcements.',
  },
  {
    name: 'Machine configuration & ordering',
    icon: Settings2,
    detail: 'Configure equipment, place machine orders and follow delivery.',
  },
  {
    name: 'Warranty & goodwill',
    icon: ShieldCheck,
    detail: 'Claims, validation and dealer reimbursement.',
  },
  {
    name: 'Technical information',
    icon: FileText,
    detail: 'Repair manuals, service bulletins, diagnostics and recall information.',
  },
  {
    name: 'Telematics',
    icon: Radio,
    detail: 'Machine operating data, location and fault information.',
  },
  {
    name: 'Dealer performance',
    icon: ChartNoAxesCombined,
    detail: 'Scorecards, targets, incentives and shared marketing programmes.',
  },
  { name: 'Training', icon: GraduationCap, detail: 'Technician learning and certification.' },
]
export function AftersalesLandscape() {
  return (
    <section className="as-position" aria-labelledby="as-position-title" id="aftersales-landscape">
      <div className="container">
        <header className="as-position__heading">
          <div>
            <p className="label">Where we fit</p>
            <h2 id="as-position-title">
              The parts journey.
              <br />
              Connected to the bigger picture.
            </h2>
          </div>
          <p>
            Our focus is parts discovery, ordering and delivery visibility. It complements the OEM’s
            wider services and the dealer’s own business systems.
          </p>
        </header>
        <div className="as-offerings">
          {offerings.map(({ icon: Icon, ...item }, i) => (
            <article key={item.name}>
              <div className="as-offerings__top">
                <Icon size={23} strokeWidth={1.5} aria-hidden="true" />
                <span>0{i + 1}</span>
              </div>
              <h3>{item.name}</h3>
              <p>{item.detail}</p>
              <Link to={item.to}>
                {item.action}
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </article>
          ))}
        </div>
        <div className="as-boundary">
          <Building2 size={21} aria-hidden="true" />
          <p>
            <strong>A connected parts experience, alongside the dealer’s systems.</strong> Dealers
            can retain their sales, rental, workshop, inventory, finance and customer-management
            tools. Shared data interfaces are the next integration step.
          </p>
          <span>Integration roadmap</span>
        </div>
        <details className="as-ecosystem">
          <summary>
            <span>Explore the OEM–dealer landscape</span>
            <span>Ownership, modules & shared data</span>
          </summary>
          <div className="as-ecosystem__body">
            <div className="as-ecosystem__columns">
              <section>
                <p className="label">OEM-provided services</p>
                <h3>The portal brings modules together.</h3>
                <p className="as-ecosystem__focus">
                  Parts catalogue, ordering, back-orders and returns sit in the parts module. This
                  demonstration covers discovery, ordering and delivery; back-order processing and
                  returns are not connected.
                </p>
                <ul>
                  {modules.map(({ icon: Icon, ...module }) => (
                    <li key={module.name}>
                      <Icon size={18} aria-hidden="true" />
                      <div>
                        <strong>{module.name}</strong>
                        <p>{module.detail}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <p className="label">Dealer-owned operations</p>
                <h3>The dealer runs its own business.</h3>
                <p>
                  A dealer management system supports day-to-day sales, rental, workshop jobs, parts
                  inventory, finance and customer relationships. The exact systems and
                  responsibilities vary by dealer network.
                </p>
                <div className="as-shared-data">
                  <Database size={22} aria-hidden="true" />
                  <h4>The data that connects them</h4>
                  <ul>
                    <li>Customers, machines and installed base</li>
                    <li>Unit sales and dealer stock</li>
                    <li>Parts sales, availability and orders</li>
                    <li>Service history and warranty claims</li>
                  </ul>
                  <p>
                    Agree identifiers, ownership and update rules first. Then connect systems so a
                    change can flow between them without duplicate entry.
                  </p>
                </div>
                <p className="as-ecosystem__note">
                  This is an illustrative architecture. These wider modules and dealer-system
                  connections are not all implemented in this demonstration.
                </p>
                <details className="as-context-sources">
                  <summary>Industry context & references</summary>
                  <a
                    href="https://www.volvoce.com/united-states/en-us/about-us/login/"
                    target="_blank"
                    rel="noreferrer"
                  >
                    OEM portal example · Volvo CE
                  </a>
                  <a href="https://www.discorp.com/" target="_blank" rel="noreferrer">
                    Dealer operations example · DIS
                  </a>
                  <a
                    href="https://www.iso.org/standard/76394.html"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Telematics data exchange · ISO/TS 15143-3
                  </a>
                  <p>
                    The telematics standard covers server-to-application data exchange for
                    applicable machinery. No telematics feed is connected here.
                  </p>
                </details>
              </section>
            </div>
          </div>
        </details>
      </div>
    </section>
  )
}
