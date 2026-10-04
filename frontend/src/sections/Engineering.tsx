import { FilmSlot } from '../components/media/FilmSlot'
import { Reveal } from '../components/Reveal'
import { films } from '../data/content'
import { useSite } from '../data/site'

export function Engineering() {
  const { data } = useSite()
  const plants = data?.plants ?? []
  const countries = new Set(plants.map((p) => p.countryCode)).size
  return (
    <section id="company" className="section engineering" aria-labelledby="engineering-title">
      <div className="container">
        <div className="engineering__head">
          <Reveal>
            <p className="label">Company</p>
            <h2 id="engineering-title" className="h1">
              Engineering across generations.
            </h2>
          </Reveal>
          <Reveal delay={120} className="engineering__text">
            <p className="lead">Noordveld has grown through acquisitions, bringing together different manufacturing organizations, machines and engineering traditions.</p>
            <p>Each brought its own machines and its own way of building them. Today they stand together under one name, with one range of machinery.</p>
          </Reveal>
        </div>

        <ol className="timeline" aria-label="How Noordveld grew">
          {plants.map((p, i) => (
            <Reveal as="li" key={p.id} className="timeline__item" delay={i * 120}>
              <span className="timeline__year">{p.acquired ?? 'Origin'}</span>
              <span className="timeline__dot" aria-hidden="true" />
              <h3 className="timeline__brand">{p.brand}</h3>
              <p>{p.acquired ? `Joined Noordveld. Machines built at ${p.city}.` : `The Noordveld range, built at ${p.city}.`}</p>
            </Reveal>
          ))}
        </ol>

        <dl className="facts">
          <div>
            <dt>Manufacturing plants</dt>
            <dd>{data ? plants.length : '–'}</dd>
          </div>
          <div>
            <dt>Countries</dt>
            <dd>{data ? countries : '–'}</dd>
          </div>
          <div>
            <dt>Machines in the range</dt>
            <dd>{data ? data.machines.length : '–'}</dd>
          </div>
        </dl>

        <Reveal className="engineering__film">
          <FilmSlot film={films.engineering} />
        </Reveal>
      </div>
    </section>
  )
}
