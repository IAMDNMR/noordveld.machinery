import { CountUp } from '../components/CountUp'
import { EditorialImage, PlantImage } from '../components/media/MachineImage'
import { FilmSlot } from '../components/media/FilmSlot'
import { films } from '../data/content'
import { useSite } from '../data/site'
import './company.css'

const chapters = [
  {
    label: '01 / ENGINEERING',
    title: 'From the first detail.',
    text: 'The machine starts with an understanding of the work. A closer look at the thinking behind its components.',
    image: 'engineering',
    alt: 'Engineering workstation inside a Noordveld plant',
  },
  {
    label: '02 / MANUFACTURING',
    title: 'Made into machinery.',
    text: 'From mechanical components to assembly. Follow the work inside the manufacturing plant.',
    image: 'work-environment',
    alt: 'Industrial work environment for Noordveld machinery',
  },
  {
    label: '03 / RELIABILITY',
    title: 'The details that matter.',
    text: 'Hydraulics, connections and mechanical systems. The parts behind a working machine.',
    image: 'mechanical-detail',
    alt: 'Close-up of hydraulic and mechanical components',
  },
]

export function Engineering() {
  const { data } = useSite()
  const plants = data?.plants ?? []
  const countries = new Set(plants.map((p) => p.countryCode)).size
  return (
    <>
      <section className="section engineering-story" aria-labelledby="engineering-story-title">
        <div className="container">
          <header className="engineering-story__heading">
            <p className="label">04 / ENGINEERED</p>
            <h2 id="engineering-story-title" className="h1">
              Engineered for
              <br />
              the real world.
            </h2>
          </header>
          <div className="engineering-story__layout">
            <div className="engineering-story__media">
              <FilmSlot film={films.engineering} />
              <div className="engineering-detail-stack">
                {chapters.map((chapter) => (
                  <figure className="engineering-detail" key={chapter.label}>
                    <EditorialImage
                      name={chapter.image}
                      subject={chapter.title}
                      ratio="16 / 9"
                      alt={chapter.alt}
                    />
                    <figcaption>{chapter.label}</figcaption>
                  </figure>
                ))}
              </div>
              <p className="media-caption">THE PROCESS BEHIND THE MACHINE</p>
              <span className="engineering-story__progress" aria-hidden="true">
                <i />
              </span>
            </div>
            <div className="engineering-chapters">
              {chapters.map((chapter) => (
                <article className="engineering-chapter" key={chapter.label}>
                  <span className="label">{chapter.label}</span>
                  <h3>{chapter.title}</h3>
                  <p>{chapter.text}</p>
                  <div className="engineering-chapter__image">
                    <EditorialImage
                      name={chapter.image}
                      subject={chapter.title}
                      ratio="16 / 9"
                      alt={chapter.alt}
                    />
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>
      <section
        id="company"
        className="section engineering company"
        aria-labelledby="engineering-title"
      >
        <div className="container">
          <div className="engineering__head">
            <div>
              <p className="label">05 / OUR COMPANY</p>
              <h2 id="engineering-title" className="h1">
                Engineering across generations.
              </h2>
            </div>
            <div className="engineering__text">
              <p className="lead">
                Noordveld has grown through acquisitions, bringing together different manufacturing
                organizations, machines and engineering traditions.
              </p>
              <p>
                Each brought its own machines and its own way of building them. Today they stand
                together under one name, with one range of machinery.
              </p>
            </div>
          </div>

          <ol className="timeline" aria-label="How Noordveld grew">
            {plants.map((p) => (
              <li key={p.id} className="timeline__item">
                <span className="timeline__year">{p.acquired ?? 'Origin'}</span>
                <span className="timeline__photo">
                  <PlantImage plant={p} ratio="4 / 3" />
                </span>
                <span className="timeline__dot" aria-hidden="true" />
                <h3 className="timeline__brand">{p.brand}</h3>
                <p>
                  {p.acquired
                    ? `Joined Noordveld. Machines built at ${p.city}.`
                    : `The Noordveld range, built at ${p.city}.`}
                </p>
              </li>
            ))}
          </ol>

          <dl className="facts">
            <div>
              <dt>Manufacturing plants</dt>
              <dd>{data ? <CountUp value={plants.length} /> : '–'}</dd>
            </div>
            <div>
              <dt>Countries</dt>
              <dd>{data ? <CountUp value={countries} /> : '–'}</dd>
            </div>
            <div>
              <dt>Machines in the range</dt>
              <dd>{data ? <CountUp value={data.machines.length} /> : '–'}</dd>
            </div>
          </dl>
        </div>
      </section>
    </>
  )
}
