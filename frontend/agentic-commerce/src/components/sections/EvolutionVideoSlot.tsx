import './evolution-video-slot.css'

const BASE = import.meta.env.BASE_URL

/** The commerce-evolution video that opens the page. Files: public/evolution-video.mp4 (1080p) and evolution-video-poster.jpg. */
export function EvolutionVideoSlot() {
  return (
    <section id="evolution-video" className="evo-slot" aria-label="Commerce evolution video">
      <div className="container">
        <video className="evo-slot__video" controls playsInline preload="metadata" poster={`${BASE}evolution-video-poster.jpg`} src={`${BASE}evolution-video.mp4`}>
          Your browser cannot play this video.
        </video>
      </div>
    </section>
  )
}
