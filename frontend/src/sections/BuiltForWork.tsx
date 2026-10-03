import { useRef } from 'react'
import { FilmSlot } from '../components/media/FilmSlot'
import { EditorialImage } from '../components/media/MachineImage'
import { Reveal } from '../components/Reveal'
import { films, industries } from '../data/content'
import { useParallax } from '../hooks/useParallax'

/** Editorial slots for brand photography. Each states what the final image shows. */
const mosaic = [
  { name: 'machinery-at-work', subject: 'Machinery at work', ratio: '4 / 5', className: 'mosaic__a', position: '70% 50%', alt: 'Noordveld machinery at work' },
  { name: 'mechanical-detail', subject: 'Mechanical detail', ratio: '1 / 1', className: 'mosaic__b', position: '40% 50%', alt: 'Close-up of a mechanical detail' },
  { name: 'engineering', subject: 'Engineering', ratio: '4 / 3', className: 'mosaic__c', position: '12% 50%', alt: 'Engineering at a Noordveld plant' },
  { name: 'work-environment', subject: 'Work environment', ratio: '16 / 9', className: 'mosaic__d', position: '62% 50%', alt: 'A working environment for Noordveld machines' },
] as const

export function BuiltForWork() {
  const mosaicRef = useRef<HTMLDivElement>(null)
  useParallax(mosaicRef, 90)
  return (
    <section id="industries" className="section on-dark built" aria-labelledby="built-title">
      <div className="container">
        <div className="built__head">
          <Reveal>
            <h2 id="built-title" className="h1">
              Built for the work that doesn’t stop.
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="lead">Machines are judged where the work happens: on the site, in the yard, on the line. Everything Noordveld builds starts from that.</p>
          </Reveal>
        </div>

        <div className="mosaic" ref={mosaicRef}>
          {mosaic.map((m, i) => (
            <Reveal key={m.subject} className={`mosaic__item ${m.className}`} delay={i * 110}>
              <EditorialImage name={m.name} subject={m.subject} ratio={m.ratio} alt={m.alt} position={'position' in m ? m.position : undefined} />
            </Reveal>
          ))}
        </div>

        <Reveal className="built__film">
          <FilmSlot film={films.machinery} />
        </Reveal>

        <div className="industries">
          <Reveal>
            <h3 className="h3 industries__title">Where Noordveld machinery works</h3>
          </Reveal>
          <ul className="industries__list">
            {industries.map((industry, i) => (
              <Reveal as="li" key={industry.name} className="industry" delay={i * 80}>
                <industry.icon size={30} strokeWidth={1.4} aria-hidden="true" />
                <h4 className="industry__name">{industry.name}</h4>
                <p>{industry.text}</p>
              </Reveal>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
