import { MachineCard } from '../components/MachineCard'
import { Reveal } from '../components/Reveal'
import { families, machines } from '../data/machines'
import { usePageMeta } from '../hooks/usePageMeta'
import './pages.css'

const slug = (family: string): string => family.toLowerCase().replace(/\s+/g, '-')

export default function MachinesPage() {
  usePageMeta({
    title: 'Machines',
    description: `The Noordveld range: ${machines.length} machines across loading, material handling and conveying, built at Assen, Lingen and Coevorden.`,
    path: '/machines',
  })
  return (
    <>
      <section className="page-head" aria-labelledby="machines-title">
        <div className="container page-head__inner">
          <Reveal>
            <p className="label">The range</p>
            <h1 id="machines-title" className="hero-title page-head__title">
              Machines built to work.
            </h1>
          </Reveal>
          <Reveal delay={120} className="page-head__side">
            <p className="lead">{machines.length} machines across loading, material handling and conveying, built at three plants in the Netherlands and Germany.</p>
            <nav aria-label="Machine families" className="jumps">
              {families.map((f) => (
                <a key={f} href={`#${slug(f)}`}>
                  {f}
                  <span>{machines.filter((m) => m.family === f).length}</span>
                </a>
              ))}
            </nav>
          </Reveal>
        </div>
      </section>

      {families.map((family) => (
        <section key={family} id={slug(family)} className="family section" aria-labelledby={`${slug(family)}-title`}>
          <div className="container">
            <Reveal className="family__head">
              <h2 id={`${slug(family)}-title`} className="h2">
                {family}
              </h2>
            </Reveal>
            <ul className="family__grid">
              {machines
                .filter((m) => m.family === family)
                .map((m, i) => (
                  <li key={m.model}>
                    <MachineCard machine={m} index={i} ratio="4 / 3" />
                  </li>
                ))}
            </ul>
          </div>
        </section>
      ))}
    </>
  )
}
