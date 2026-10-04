import { ButtonLink } from '../ui/ButtonLink'
import { Reveal } from '../ui/Reveal'
import './agentic.css'

/**
 * The idea, not the data: a need, the constraints around it, the options the agent weighs and the action it recommends.
 * Deliberately abstract (no machine, part, price or supplier); the real thing runs on Noordveld data in Agentic Shopping.
 */
const CONSTRAINTS = ['Budget', 'Urgency', 'Availability', 'Location']
const OPTIONS = [
  ['Option A', 'Best availability'],
  ['Option B', 'Fastest fulfilment'],
  ['Option C', 'Lowest cost'],
]

export function AgenticIntro() {
  return (
    <section id="agentic" className="section on-night agentic-intro" aria-labelledby="agentic-title">
      <div className="container">
        <Reveal>
          <p className="eyebrow">What comes next</p>
        </Reveal>
        <Reveal delay={80}>
          <h2 id="agentic-title" className="display agentic-intro__title">
            Agentic E-Commerce
          </h2>
        </Reveal>
        <Reveal delay={160}>
          <p className="lead agentic-intro__lead">Every earlier chapter of commerce started with a product the customer already had in mind. This one starts with a need, and the constraints that come with it.</p>
        </Reveal>

        <ol className="concept" aria-label="How an agent turns a need into an action">
          <Reveal as="li" className="concept__step" delay={0}>
            <p className="concept__label">User need</p>
            <p className="concept__need">“My machine is down.”</p>
          </Reveal>
          <Reveal as="li" className="concept__step" delay={120}>
            <p className="concept__label">Constraints</p>
            <ul className="concept__chips">
              {CONSTRAINTS.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </Reveal>
          <Reveal as="li" className="concept__step" delay={240}>
            <p className="concept__label">Agent evaluates</p>
            <ul className="concept__options">
              {OPTIONS.map(([name, trait], i) => (
                <li key={name} className={i === 0 ? 'is-best' : ''}>
                  <strong>{name}</strong>
                  <span>{trait}</span>
                </li>
              ))}
            </ul>
          </Reveal>
          <Reveal as="li" className="concept__step concept__step--action" delay={360}>
            <p className="concept__label">Recommended action</p>
            <p className="concept__action">The option that best meets every constraint, checked and ready to order.</p>
          </Reveal>
        </ol>

        <Reveal className="concept__foot" delay={480}>
          <p className="requirement__note">A conceptual illustration. It shows no real machine, part or price.</p>
          <ButtonLink href="/agentic-shopping">See it work with real Noordveld data</ButtonLink>
        </Reveal>
      </div>
    </section>
  )
}
