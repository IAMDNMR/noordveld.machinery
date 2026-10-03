import { ArrowDown } from 'lucide-react'
import { useRef, type CSSProperties } from 'react'
import { editorialImageUrl } from '../../../../src/lib/assets'
import { useInView } from '../../hooks/useInView'
import { NoBreakName } from '../ui/NoBreakName'
import { THEORY_LEAD, THEORY_NEXT, THEORY_OUTRO, THEORY_STAGES, THEORY_TITLE, type TheoryStage } from './theory-data'
import './theory.css'

/** Reveals its children in sequence once it is in view. Delays come from the `--d` custom property of each `.rv`. */
function Stage({ stage }: { stage: TheoryStage }) {
  const ref = useRef<HTMLElement>(null)
  const seen = useInView(ref, { once: true, threshold: 0.28, rootMargin: '0px 0px -6% 0px' })
  const img = editorialImageUrl(stage.image)
  const d = (n: number): CSSProperties => ({ ['--d' as string]: `${n}ms` })
  return (
    <article ref={ref} className={`stage ${seen ? 'is-in' : ''} ${stage.id === 'agentic-commerce' ? 'is-agentic' : ''}`} aria-labelledby={`stage-${stage.id}`}>
      <div className="stage__rail" aria-hidden="true">
        <i className="stage__dot" />
        <i className="stage__line" />
      </div>

      <header className="stage__head">
        <p className="stage__no rv" style={d(0)}>
          <span>{stage.no}</span>
        </p>
        <h3 id={`stage-${stage.id}`} className="stage__name rv" style={d(80)}>
          <NoBreakName name={stage.name} />
        </h3>
        <p className="stage__statement rv" style={d(200)}>
          {stage.statement}
        </p>
      </header>

      <div className="stage__body">
        <p className="stage__text rv" style={d(280)}>
          {stage.body}
        </p>
        <ul className="stage__traits" aria-label={`${stage.name}: characteristics`}>
          {stage.traits.map((t, i) => (
            <li key={t} className="rv" style={d(380 + i * 70)}>
              {t}
            </li>
          ))}
        </ul>
        <div className="stage__idea rv" style={d(560)}>
          <span className="stage__idea-label">The core idea</span>
          <p>{stage.idea}</p>
        </div>
      </div>

      {img ? (
        <figure className="stage__fig">
          <img src={img} alt={stage.imageAlt} loading="lazy" decoding="async" />
        </figure>
      ) : null}
    </article>
  )
}

export function Theory() {
  return (
    <section id="theory" className="theory" aria-labelledby="theory-title">
      <div className="container">
        <header className="theory__head">
          <h2 id="theory-title" className="theory__title">
            {THEORY_TITLE}
          </h2>
          <p className="theory__lead">{THEORY_LEAD}</p>
        </header>

        <div className="theory__stages">
          {THEORY_STAGES.map((s) => (
            <Stage key={s.id} stage={s} />
          ))}
        </div>

        <footer className="theory__outro">
          <p className="theory__outro-line" aria-label={THEORY_OUTRO.join(' ')}>
            {THEORY_OUTRO.map((l, i) => (
              <span key={l} className={i === 1 ? 'is-teal' : ''} aria-hidden="true">
                {l}
              </span>
            ))}
          </p>
          <p className="theory__next">{THEORY_NEXT}</p>
          <a className="theory__arrow" href="#evolution" aria-label="Go to the Agentic Commerce demo">
            <ArrowDown size={22} strokeWidth={1.6} aria-hidden="true" />
          </a>
        </footer>
      </div>
    </section>
  )
}
