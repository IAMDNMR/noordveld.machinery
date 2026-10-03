import { useRef } from 'react'
import { useActiveIndex } from '../../hooks/useActiveIndex'
import { processSteps } from '../../data/process'
import { Reveal } from '../ui/Reveal'
import { RelationshipMap } from './RelationshipMap'

export function Process() {
  const listRef = useRef<HTMLOListElement>(null)
  const active = useActiveIndex(listRef, '[data-step]')

  return (
    <section className="section on-night process" aria-labelledby="process-title">
      <div className="container">
        <Reveal>
          <h2 id="process-title" className="h1 process__title">
            From a sentence to a decision.
          </h2>
        </Reveal>
        <Reveal delay={100}>
          <p className="lead process__lead">The customer says what they need. The system works through it the way a good specialist would, and keeps the customer in control of the final call.</p>
        </Reveal>

        <div className="process__layout">
          <div className="process__map">
            <RelationshipMap step={active} stepCount={processSteps.length} />
          </div>
          <ol className="process__steps" ref={listRef}>
            {processSteps.map((s, i) => (
              <li key={s.id} data-step className={`process__step ${i === active ? 'is-active' : ''}`} aria-current={i === active ? 'step' : undefined}>
                <s.icon className="process__index" size={36} strokeWidth={1.4} aria-hidden="true" />
                <h3 className="process__name">{s.name}</h3>
                <p className="process__question">{s.question}</p>
                {s.detail ? <p className="process__detail">{s.detail}</p> : null}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  )
}
