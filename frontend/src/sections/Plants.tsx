import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PlantImage } from '../components/media/MachineImage'
import { Reveal } from '../components/Reveal'
import { machinesAt, plants } from '../data/machines'
import type { PlantId } from '../types/catalog'
import { PlantMap } from './PlantMap'

export function Plants() {
  const [active, setActive] = useState<PlantId>('assen')

  return (
    <section id="plants" className="section on-mist plants" aria-labelledby="plants-title">
      <div className="container">
        <Reveal className="plants__head">
          <h2 id="plants-title" className="h1">
            Three plants. Two countries.
          </h2>
          <p className="lead">Every Noordveld machine comes from one of three plants in the north of the Netherlands and Germany.</p>
        </Reveal>

        <div className="plants__layout">
          <div className="plants__map">
            <PlantMap active={active} onSelect={setActive} />
          </div>
          <ul className="plants__list">
            {plants.map((plant) => {
              const list = machinesAt(plant.id)
              return (
                <li key={plant.id} className={`plant ${active === plant.id ? 'is-active' : ''}`} onPointerEnter={() => setActive(plant.id)} onFocusCapture={() => setActive(plant.id)}>
                  <PlantImage plant={plant} ratio="16 / 8" />
                  <div className="plant__body">
                    <div className="plant__title">
                      <h3 className="h3">
                        {plant.city}, {plant.country}
                      </h3>
                      <p className="plant__brand">
                        {plant.brand}
                        {plant.acquired ? ` · acquired ${plant.acquired}` : ''}
                      </p>
                    </div>
                    <p className="plant__models">
                      {list.map((m, i) => (
                        <span key={m.model}>
                          <Link to={`/machines/${m.slug}`}>{m.model}</Link>
                          {i < list.length - 1 ? ', ' : ''}
                        </span>
                      ))}
                    </p>
                    <p className="plant__types">{list.map((m) => m.name).join(' · ')}</p>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </section>
  )
}
