import type { ReactNode } from 'react'
import { IntroVideo } from './IntroVideo'
import { ArrowRight, Database, Link2, ScanLine } from 'lucide-react'

/** The page header: what Parts Intelligence does, a link to the introduction film, then the question area passed in as children. */
export function PiHero({ children }: { children: ReactNode }) {
  return (
    <header className="pih-hero">
      <div className="wf-container">
        <div className="pih-hero__inner">
          <div className="pih-hero__heading">
            <div>
              <p className="eyebrow">Noordveld · Parts Intelligence</p>
              <h1 id="pi-title">Meet Spark.</h1>
              <p className="lede">
                Your parts intelligence expert. Ask about parts, machine compatibility and supply
                options. Every answer links back to its source.
              </p>
            </div>
            <aside className="pi-evidence" aria-label="How answers are found">
              <p className="eyebrow">From question to evidence</p>
              <ol>
                <li>
                  <ScanLine size={20} aria-hidden="true" />
                  <span>Identify the part</span>
                </li>
                <li>
                  <Link2 size={20} aria-hidden="true" />
                  <span>Follow its connections</span>
                </li>
                <li>
                  <Database size={20} aria-hidden="true" />
                  <span>Check the source</span>
                </li>
              </ol>
              <p>
                Fitment. Suppliers. Stock. One connected view.
                <ArrowRight size={16} aria-hidden="true" />
              </p>
            </aside>
          </div>
          <IntroVideo />
          <div className="pih-hero__ask">{children}</div>
        </div>
      </div>
    </header>
  )
}
