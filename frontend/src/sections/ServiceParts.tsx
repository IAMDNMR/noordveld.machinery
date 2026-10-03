import { Cog, LifeBuoy, Timer, Wrench, type LucideIcon } from 'lucide-react'
import { ButtonLink } from '../components/ButtonLink'
import { FilmSlot } from '../components/media/FilmSlot'
import { EditorialImage } from '../components/media/MachineImage'
import { Reveal } from '../components/Reveal'
import { company, films } from '../data/content'
import { parts, partCategories } from '../data/machines'

const concepts: readonly { name: string; text: string; icon: LucideIcon }[] = [
  { name: 'Service', text: 'People who know the machine.', icon: Wrench },
  { name: 'Maintenance', text: 'Keeping the machine in shape for the next job.', icon: Cog },
  { name: 'Support', text: 'Someone to ask when something is not right.', icon: LifeBuoy },
  { name: 'Uptime', text: 'The point of all of it: a machine that is working.', icon: Timer },
]

export function Service() {
  return (
    <section id="service" className="section service" aria-labelledby="service-title">
      <div className="container service__layout">
        <div className="service__copy">
          <Reveal>
            <p className="label">Service &amp; support</p>
            <h2 id="service-title" className="h1">
              Support that stays with the machine.
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="lead">A machine is only as good as the support behind it. Service, maintenance, parts and support work together to keep Noordveld machinery running.</p>
          </Reveal>
          <ul className="concepts">
            {concepts.map((c, i) => (
              <Reveal as="li" key={c.name} className="concept" delay={i * 80}>
                <c.icon size={26} strokeWidth={1.5} aria-hidden="true" />
                <div>
                  <h3 className="concept__name">{c.name}</h3>
                  <p>{c.text}</p>
                </div>
              </Reveal>
            ))}
          </ul>
          <Reveal>
            <ButtonLink to={`mailto:${company.serviceEmail}?subject=Service%20enquiry`} external>
              Explore Service
            </ButtonLink>
          </Reveal>
        </div>
        <Reveal className="service__media" delay={160}>
          <EditorialImage name="service" subject="Service" ratio="4 / 5" alt="A Noordveld service engineer at work" position="74% 50%" />
        </Reveal>
      </div>
      <div className="container service__film">
        <Reveal>
          <FilmSlot film={films.service} />
        </Reveal>
      </div>
    </section>
  )
}

export function PartsSection() {
  return (
    <section id="parts" className="section on-mist parts" aria-labelledby="parts-title">
      <div className="container parts__layout">
        <div className="parts__copy">
          <Reveal>
            <p className="label">Parts &amp; commerce</p>
            <h2 id="parts-title" className="h1">
              The right part matters.
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="lead">Every machine depends on the parts behind it. Noordveld brings machine and parts information together to make finding the right component easier.</p>
          </Reveal>
          <Reveal>
            <ButtonLink to="/parts-store">Shop Parts</ButtonLink>
          </Reveal>
        </div>
        <Reveal className="parts__catalogue" delay={160}>
          <p className="parts__count">
            <strong>{parts.length}</strong> parts catalogued across {partCategories.length} categories
          </p>
          <ul className="parts__list">
            {partCategories.map((c) => (
              <li key={c.name}>
                <span>{c.name}</span>
                <span className="parts__n">{c.count}</span>
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </section>
  )
}
