import { useRef } from 'react'
import { useInView } from '../../hooks/useInView'
import { Reveal } from '../ui/Reveal'

export function Outcome() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, threshold: 0.4 })

  return (
    <section className="section on-night outcome" aria-labelledby="outcome-title">
      <div className="container outcome__inner" ref={ref}>
        <svg className={`outcome__mark ${inView ? 'is-in' : ''}`} viewBox="0 0 120 120" aria-hidden="true" fill="none">
          <circle className="outcome__ring" cx="60" cy="60" r="52" pathLength={1} />
          <path className="outcome__tick" d="M36 62l16 16 32-36" pathLength={1} />
        </svg>
        <Reveal>
          <h2 id="outcome-title" className="display outcome__title">
            Machine operational.
          </h2>
        </Reveal>
        <Reveal delay={140}>
          <p className="lead outcome__lead">The objective was never simply to find a part. The objective was to solve the problem.</p>
        </Reveal>
      </div>
    </section>
  )
}
