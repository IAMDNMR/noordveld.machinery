import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { ButtonLink } from '../components/ButtonLink'
import { FilmSlot } from '../components/media/FilmSlot'
import { EditorialImage } from '../components/media/MachineImage'
import { films } from '../data/content'
import { useSite } from '../data/site'

const topics = [
  { name: 'Service', text: 'People who know the machine, and the work it needs to do.' },
  { name: 'Maintenance', text: 'Keeping the machine in shape for the next job.' },
  { name: 'Technical support', text: 'Someone to ask when something is not right.' },
  {
    name: 'Uptime',
    text: 'Parts, maintenance and support working towards one goal: a machine that is working.',
  },
]

export function Service() {
  return (
    <section id="service" className="section service" aria-labelledby="service-title">
      <div className="container">
        <header className="service__heading">
          <div>
            <p className="label">06 / AFTERSALES</p>
            <h2 id="service-title" className="h1">
              Support that stays
              <br />
              with the machine.
            </h2>
          </div>
          <EditorialImage
            name="service"
            subject="Service"
            ratio="16 / 9"
            alt="A Noordveld service engineer at work"
            position="74% 50%"
          />
        </header>
      </div>
      <div className="service__cinema">
        <FilmSlot film={films.service} />
      </div>
      <div className="container service__narrative">
        <p className="media-caption">HUMAN EXPERTISE. MACHINE UPTIME.</p>
        <ol className="service-topics">
          {topics.map((topic, i) => (
            <li key={topic.name}>
              <span>0{i + 1}</span>
              <h3>{topic.name}</h3>
              <p>{topic.text}</p>
            </li>
          ))}
        </ol>
        <div className="service__closing">
          <p>
            For the next job.
            <br />
            And the one after that.
          </p>
          <ButtonLink to="/parts-services">Explore Aftersales</ButtonLink>
        </div>
      </div>
    </section>
  )
}

export function PartsSection() {
  const { data } = useSite()
  const partCategories = data?.partCategories ?? []
  return (
    <section id="parts" className="section on-mist parts" aria-labelledby="parts-title">
      <div className="container parts__layout">
        <div className="parts__copy">
          <div>
            <p className="label">07 / PARTS &amp; COMMERCE</p>
            <h2 id="parts-title" className="h1">
              Every component matters.
            </h2>
          </div>
          <div>
            <p className="lead">
              Every machine depends on the parts behind it. Noordveld brings machine and parts
              information together to make finding the right component easier.
            </p>
          </div>
          <div>
            <ButtonLink to="/parts-store">Open Parts Portal</ButtonLink>
          </div>
        </div>
        <div className="parts__catalogue">
          <p className="parts__count">
            {data ? (
              <>
                <strong>{data.partCount}</strong> parts catalogued across {partCategories.length}{' '}
                categories
              </>
            ) : (
              'Loading the catalogue…'
            )}
          </p>
          <ul className="parts__list">
            {partCategories.map((c, index) => (
              <li key={c.name}>
                <Link to={`/parts-store?category=${encodeURIComponent(c.name)}`}>
                  <span className="parts__ordinal">{String(index + 1).padStart(2, '0')}</span>
                  <span>{c.name}</span>
                  <span className="parts__n">{c.count}</span>
                  <ArrowUpRight size={18} aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
