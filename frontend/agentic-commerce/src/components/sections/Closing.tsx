import { ButtonLink } from '../ui/ButtonLink'
import { Reveal } from '../ui/Reveal'
import './closing.css'

export function Closing() {
  return (
    <section id="about" className="section on-night closing" aria-labelledby="closing-title">
      <div className="container closing__inner">
        <Reveal>
          <h2 id="closing-title" className="display closing__title">
            The next evolution of commerce <span className="accent-text">is intelligent action.</span>
          </h2>
        </Reveal>
        <Reveal delay={140}>
          <p className="lead closing__lead">Agentic E-Commerce moves beyond helping customers find products. It understands requirements, evaluates available options against real-world constraints, recommends a suitable path, and helps turn that decision into action.</p>
        </Reveal>
        <Reveal delay={260}>
          <div className="closing__actions">
            <ButtonLink href="/agentic-shopping">See it work with real Noordveld data</ButtonLink>
            <ButtonLink href="#evolution" variant="secondary">
              Watch the demo
            </ButtonLink>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
