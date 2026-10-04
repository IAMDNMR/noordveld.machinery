import type { ReactNode } from 'react'
import { IntroVideo } from './IntroVideo'

/** The page header: what Parts Intelligence does, a link to the introduction film, then the question area passed in as children. */
export function PiHero({ children }: { children: ReactNode }) {
  return (
    <header className="pih-hero">
      <div className="wf-container">
        <div className="pih-hero__inner">
          <p className="eyebrow">Parts Intelligence</p>
          <h1 id="pi-title">
            Ask about any part, machine or relationship.
          </h1>
          <p className="lede">Answers are read from the relationships in the parts knowledge graph, and every result shows where its data comes from.</p>
          <IntroVideo />
          <div className="pih-hero__ask">{children}</div>
        </div>
      </div>
    </header>
  )
}
