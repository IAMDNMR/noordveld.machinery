import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MachineImage } from '../components/media/MachineImage'
import { MachineCard } from '../components/MachineCard'
import { Reveal } from '../components/Reveal'
import { BarChart, CineHero, Donut } from '../components/cine/Cine'
import { Tilt } from '../components/cine/Tilt'
import { machineImageUrl } from '../lib/assets'
import { capitalise, countWord, inText, useSite } from '../data/site'
import { usePageMeta } from '../hooks/usePageMeta'
import './pages.css'
import './machines.css'

const slug = (family: string): string => family.toLowerCase().replace(/\s+/g, '-')

export default function MachinesPage() {
  const { data } = useSite()
  const machines = data?.machines ?? []
  const families = data?.families ?? []
  const plants = data?.plants ?? []
  const [active, setActive] = useState<string>('all')
  const shown = active === 'all' ? families : families.filter((f) => f === active)
  const countries = [...new Set(plants.map((p) => p.country))]
  usePageMeta({
    title: 'Machines',
    description: data
      ? `The Noordveld range: ${machines.length} machines across the ${families.join(', ')}, built at ${plants.map((p) => p.city).join(', ')}.`
      : 'The Noordveld range of machines.',
    path: '/machines',
  })
  return (
    <>
      <CineHero
        id="machines-title"
        eyebrow="The range"
        lines={['Machines', 'built to work.']}
        image={machines[0] ? machineImageUrl(machines[0].slug) : undefined}
        lead={
          data ? (
            <p>
              {machines.length} machines across the {families.join(', ')}, built at{' '}
              {countWord(plants.length)} plants in {countries.map(inText).join(' and ')}.
            </p>
          ) : (
            <p>Loading the range…</p>
          )
        }
        stats={
          data
            ? [
                { value: machines.length, label: 'Machine models' },
                { value: families.length, label: 'Families' },
                { value: plants.length, label: 'Plants' },
                { value: countries.length, label: 'Countries' },
              ]
            : undefined
        }
      >
        <nav aria-label="Machine families" className="filters cine-filters">
          {['all', ...families].map((f) => (
            <button key={f} type="button" aria-pressed={active === f} onClick={() => setActive(f)}>
              {f === 'all' ? 'All' : f}
              <span>
                {f === 'all' ? machines.length : machines.filter((m) => m.family === f).length}
              </span>
            </button>
          ))}
        </nav>
      </CineHero>
      <section className="range-opening range-opening--feature" aria-label="Featured machine">
        {machines[0] ? (
          <div className="container range-opening__feature">
            <MachineImage machine={machines[0]} ratio="21 / 9" eager />
            <Link to={`/machines/${machines[0].slug}`}>
              <span>{machines[0].model}</span>
              <strong>{machines[0].name}</strong>
              <span>View machine ↗</span>
            </Link>
          </div>
        ) : null}
      </section>

      {data ? (
        <section className="range-glance cine-dark" aria-labelledby="range-glance-title">
          <div className="container range-glance__layout">
            <header>
              <p className="cine-eyebrow">The range at a glance</p>
              <h2 id="range-glance-title">
                {capitalise(countWord(families.length))}{' '}
                {families.length === 1 ? 'family' : 'families'}. <em>One standard of build.</em>
              </h2>
              <p>
                Where each model is built and how the range divides across families, from the
                recorded catalogue. Choose a family to see its share.
              </p>
            </header>
            <Tilt className="range-glance__card" max={4}>
              <h3>Models per family</h3>
              <Donut
                label="Machine models per family"
                rows={families.map((f) => ({
                  name: f,
                  value: machines.filter((m) => m.family === f).length,
                }))}
                total="models"
              />
            </Tilt>
            <Tilt className="range-glance__card" max={4}>
              <h3>Models per plant</h3>
              <BarChart
                label="Machine models per plant"
                rows={plants
                  .map((p) => ({ name: `${p.city} · ${p.brand}`, value: p.machineCount }))
                  .sort((a, b) => b.value - a.value)}
              />
            </Tilt>
          </div>
        </section>
      ) : null}

      {shown.map((family) => (
        <section
          key={family}
          id={slug(family)}
          className="family section is-filtered"
          aria-labelledby={`${slug(family)}-title`}
        >
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
                  <li key={m.model} className={i === 0 ? 'is-feature' : undefined}>
                    <MachineCard machine={m} index={i} ratio={i === 0 ? '16 / 9' : '4 / 3'} />
                  </li>
                ))}
            </ul>
          </div>
        </section>
      ))}
    </>
  )
}
