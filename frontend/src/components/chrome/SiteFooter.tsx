import { company, nav } from '../../data/content'
import { Logo } from '../Logo'
import './chrome-tokens.css'
import './chrome.css'
import type { ChromeLink } from './links'

export function SiteFooter({ Link }: { Link: ChromeLink }) {
  return (
    <footer className="footer nvx-chrome">
      <div className="nvx-container footer__grid">
        <div className="footer__brand">
          <Logo tone="light" height={38} />
          <p>Industrial and agricultural machinery from Assen, Lingen and Coevorden.</p>
        </div>
        <nav aria-label="Footer" className="footer__col">
          <h2 className="footer__heading">Explore</h2>
          <ul>
            {nav.map((item) => (
              <li key={item.label}>
                <Link to={item.to} external={item.external}>
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="footer__col">
          <h2 className="footer__heading">Contact</h2>
          <ul>
            <li>
              <a href={`mailto:${company.email}`}>{company.email}</a>
            </li>
            <li>
              <a href={`mailto:${company.serviceEmail}`}>{company.serviceEmail}</a>
            </li>
          </ul>
        </div>
        <div className="footer__col">
          <h2 className="footer__heading">Legal</h2>
          <ul>
            <li>
              <Link to="/legal">Legal</Link>
            </li>
            <li>
              <Link to="/privacy">Privacy</Link>
            </li>
          </ul>
        </div>
      </div>
      <div className="nvx-container footer__base">
        <p>© Noordveld Machinery B.V.</p>
        <p>{company.disclaimer}</p>
      </div>
    </footer>
  )
}
