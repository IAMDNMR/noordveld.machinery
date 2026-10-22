import './evolution-video-slot.css'

const BASE = import.meta.env.BASE_URL

/** The commerce-evolution video that opens the page. Files: public/evolution-video.mp4 (1080p) and evolution-video-poster.jpg. */
export function EvolutionVideoSlot() {
  return (
    <section id="evolution-video" className="evo-slot" aria-label="Commerce evolution video">
      <div className="container">
        {/* The existing supplied film has no verified caption asset; do not invent a transcript. */}
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video
          className="evo-slot__video"
          controls
          playsInline
          preload="metadata"
          poster={`${BASE}evolution-video-poster.jpg`}
          src={`${BASE}evolution-video.mp4?v=20261022`}
        >
          Your browser cannot play this video.
        </video>
      </div>
    </section>
  )
}
