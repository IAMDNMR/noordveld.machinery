import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Machine } from '../types/catalog'
import { MachineImage } from './media/MachineImage'
import './machine-card.css'

interface MachineCardProps {
  machine: Machine
  ratio?: string
  /** Staggers the image reveal */
  index?: number
}

/** One machine: image, model, name, category and origin. The whole card is one link to its page. */
export function MachineCard({ machine, ratio = '4 / 3', index = 0 }: MachineCardProps) {
  return (
    <Link className="mcard" to={`/machines/${machine.slug}`} aria-label={`${machine.model}, ${machine.name}`}>
      <div className="mcard__media">
        <MachineImage machine={machine} ratio={ratio} reveal revealDelay={(index % 4) * 90} />
        <span className="mcard__go" aria-hidden="true">
          <ArrowUpRight size={20} strokeWidth={2} />
        </span>
      </div>
      <div className="mcard__body">
        <p className="mcard__model">{machine.model}</p>
        <h3 className="mcard__name">{machine.name}</h3>
        <p className="mcard__meta">
          {machine.family} · {machine.plant}
        </p>
        <p className="mcard__origin">
          <span>{machine.brand}</span>
          <span className="mcard__explore">Explore</span>
        </p>
      </div>
    </Link>
  )
}
