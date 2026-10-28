import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { FilmSlot } from '../components/media/FilmSlot'
import { EditorialImage, MachineImage } from '../components/media/MachineImage'
import { films, industries } from '../data/content'
import { useSite } from '../data/site'
import { useMediaQuery } from '../hooks/useMediaQuery'

export function BuiltForWork() {
  const [active, setActive] = useState(0)
  const { data } = useSite()
  const compact = useMediaQuery('(max-width: 759px)')
  const types = [
    'Electric Forklift',
    'Belt Conveyor Module',
    'Reach Truck',
    'Wheel Loader',
    'Telehandler',
  ]
  const selectedMachine = data?.machines.find((machine) => machine.name === types[active])
  const visual = selectedMachine ? (
    <MachineImage machine={selectedMachine} ratio="4 / 5" />
  ) : (
    <EditorialImage
      name="work-environment"
      subject="Work environment"
      ratio="4 / 5"
      alt="Noordveld machinery in a working environment"
    />
  )
  return (
    <>
      <section id="at-work" className="built on-dark" aria-labelledby="built-title">
        <div className="built__stage">
          <div className="built__intro container">
            <p className="label">02 / AT WORK</p>
            <h2 id="built-title" className="h1">
              Built for the work
              <br />
              that doesn’t stop.
            </h2>
            <p>On the site. In the yard. On the line.</p>
          </div>
          <div className="built__window">
            <FilmSlot film={films.machinery} />
          </div>
          <p className="built__caption container">
            <span>NOORDVELD IN MOTION</span>
            <span>Performance where it matters.</span>
          </p>
        </div>
      </section>
      <section
        id="industries"
        className="section applications"
        aria-labelledby="applications-title"
      >
        <div className="container applications__layout">
          <div className="applications__index">
            <p className="label">03 / APPLICATIONS</p>
            <h2 id="applications-title" className="h1">
              Where Noordveld works.
            </h2>
            <ol className="industry-index">
              {industries.map((industry, i) => (
                <li key={industry.name} className={active === i ? 'is-current' : ''}>
                  <button
                    type="button"
                    aria-expanded={compact ? active === i : undefined}
                    aria-pressed={compact ? undefined : active === i}
                    aria-controls={compact ? `industry-panel-${i}` : 'industry-visual'}
                    onClick={() => setActive(i)}
                    onFocus={() => {
                      if (!compact) setActive(i)
                    }}
                    onPointerEnter={(event) => {
                      if (event.pointerType === 'mouse' && !compact) setActive(i)
                    }}
                  >
                    <span>0{i + 1}</span>
                    <strong>{industry.name}</strong>
                    <ArrowUpRight size={20} aria-hidden="true" />
                  </button>
                  <div id={`industry-panel-${i}`} hidden={active !== i}>
                    <p>{industry.text}</p>
                    <div className="industry-index__image">{active === i ? visual : null}</div>
                  </div>
                </li>
              ))}
            </ol>
            <Link className="text-link" to="/machines">
              Explore the machinery range <ArrowUpRight size={18} aria-hidden="true" />
            </Link>
          </div>
          <figure id="industry-visual" className="applications__visual" key={active}>
            {visual}
            <figcaption>
              <span>
                0{active + 1} / {industries[active].name}
              </span>
              <span>NOORDVELD</span>
            </figcaption>
            <p className="applications__description">{industries[active].text}</p>
          </figure>
        </div>
      </section>
    </>
  )
}
