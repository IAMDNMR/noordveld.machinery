import './launch.css'

/** The supplied workflow film; playback never depends on loading the catalogue. */
export function LaunchFilm() {
  return (
    <section className="launch launch--supplied" aria-labelledby="workflow-film-title">
      <div className="container">
        <header>
          <p className="eyebrow">The workflow</p>
          <h2 id="workflow-film-title">From a request to the right next step.</h2>
        </header>
        {/* The supplied video has no caption file. Do not invent a transcript. */}
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video
          controls
          playsInline
          preload="metadata"
          poster={`${import.meta.env.BASE_URL}agentic-workflow-poster.jpg`}
          src={`${import.meta.env.BASE_URL}agentic-workflow-film.mp4`}
          aria-label="Agentic e-commerce workflow film"
        >
          Your browser cannot play this video.
        </video>
      </div>
    </section>
  )
}
