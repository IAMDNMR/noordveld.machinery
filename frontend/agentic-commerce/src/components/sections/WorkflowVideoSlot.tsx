import './workflow-video-slot.css'

const BASE = import.meta.env.BASE_URL

/**
 * The end-to-end workflow film (rendered from agentic-commerce/src/film/workflow with the real application screens, voice-over and music).
 * Files: public/agentic-workflow-film.mp4, agentic-workflow-film.jpg (poster) and agentic-workflow-film.vtt (captions of the voice-over).
 */
export function WorkflowVideoSlot() {
  return (
    <section className="wf-slot" aria-label="Agentic E-Commerce workflow film">
      <div className="container">
        <video
          className="wf-slot__video"
          controls
          playsInline
          preload="metadata"
          poster={`${BASE}agentic-workflow-film.jpg`}
          src={`${BASE}agentic-workflow-film.mp4`}
        >
          <track
            kind="captions"
            srcLang="en"
            label="English"
            src={`${BASE}agentic-workflow-film.vtt`}
          />
          Your browser cannot play this video.
        </video>
      </div>
    </section>
  )
}
