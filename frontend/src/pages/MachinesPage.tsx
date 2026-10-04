import { MachineCard } from '../components/MachineCard'
import { Reveal } from '../components/Reveal'
import { countWord, inText, useSite } from '../data/site'
import { usePageMeta } from '../hooks/usePageMeta'
import './pages.css'

const slug = (family: string): string => family.toLowerCase().replace(/\s+/g, '-')

export default function MachinesPage() {
  const { data } = useSite()
  const machines = data?.machines ?? []
  const families = data?.families ?? []
  const plants = data?.plants ?? []
  const countries = [...new Set(plants.map((p) => p.country))]
  usePageMeta({
    title: 'Machines',
    description: data ? `The Noordveld range: ${machines.length} machines across the ${families.join(', ')}, built at ${plants.map((p) => p.city).join(', ')}.` : 'The Noordveld range of machines.',
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
            {data ? (
              <p className="lead">
                {machines.length} machines across the {families.join(', ')}, built at {countWord(plants.length)} plants in {countries.map(inText).join(' and ')}.
              </p>
            ) : (
              <p className="lead">Loading the range…</p>
            )}
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
