import { stages } from '../../data/stages'
import { NoBreakName } from '../ui/NoBreakName'
import { Reveal } from '../ui/Reveal'
import './closing.css'

const lines: Record<string, string> = {
  commerce: 'I need something.',
  'e-commerce': 'I know what I want. Help me buy it online.',
  'quick-commerce': 'I know what I want. Get it to me quickly.',
  'agentic-e-commerce': 'I have a need. Understand it, find the right solution, and help me achieve the outcome.',
}

export function Comparison() {
  return (
    <section id="theory" className="section comparison" aria-labelledby="comparison-title">
      <div className="container">
        <Reveal>
          <h2 id="comparison-title" className="h1 comparison__title">
            Four eras of what customers expect.
          </h2>
        </Reveal>
        <ol className="comparison__list">
          {stages.map((s, i) => (
            <li key={s.id} className="comparison__item">
              <Reveal delay={i * 120}>
                <span className="comparison__rule" aria-hidden="true" />
                <h3 className="comparison__name"><NoBreakName name={s.name} /></h3>
                <p className="comparison__line">{lines[s.id]}</p>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
