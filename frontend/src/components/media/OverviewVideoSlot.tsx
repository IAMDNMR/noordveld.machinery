import { Film } from 'lucide-react'
import './overview-video-slot.css'

/** A stable 16:9 space for the overview film the user will supply. */
export function OverviewVideoSlot({ title }: { title: string }) {
  return (
    <div className="overview-video-slot" role="img" aria-label={`${title} — video coming soon`}>
      <span className="overview-video-slot__icon" aria-hidden="true">
        <Film size={28} strokeWidth={1.4} />
      </span>
      <p>{title}</p>
      <span className="overview-video-slot__status">Overview film · coming soon</span>
    </div>
  )
}
