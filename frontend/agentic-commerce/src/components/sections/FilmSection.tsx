import { useEffect, useRef } from 'react'
import { queries } from '../../lib/breakpoints'
import { useInView } from '../../hooks/useInView'
import { useMediaQuery, useReducedMotion } from '../../hooks/useMediaQuery'
import { Reveal } from '../ui/Reveal'
import './film-section.css'

/** Rendered from the Remotion composition (see README). The square cut is used on phones. */
const FILMS = {
  landscape: { src: `${import.meta.env.BASE_URL}evolution-film-16x9.mp4`, poster: `${import.meta.env.BASE_URL}evolution-film-16x9.jpg`, ratio: '16 / 9' },
  square: { src: `${import.meta.env.BASE_URL}evolution-film-1x1.mp4`, poster: `${import.meta.env.BASE_URL}evolution-film-1x1.jpg`, ratio: '1 / 1' },
} as const

interface FilmVideoProps {
  src: string
  poster: string
  reduced: boolean
}

/** Autoplays (muted, looping) while on screen and pauses off screen. No clicks needed. */
function FilmVideo({ src, poster, reduced }: FilmVideoProps) {
  const ref = useRef<HTMLVideoElement>(null)
  const inView = useInView(ref, { threshold: 0.35 })

  useEffect(() => {
    const video = ref.current
    if (!video || reduced) return
    if (inView) void video.play().catch(() => undefined)
    else video.pause()
  }, [inView, reduced])

  return (
    <video
      ref={ref}
      className="film-section__video"
      src={src}
      poster={poster}
      muted
      loop
      playsInline
      preload="none"
      controls={reduced}
      aria-label="Film: commerce, e-commerce, quick commerce and agentic e-commerce."
    />
  )
}

export function FilmSection() {
  const reduced = useReducedMotion()
  const compact = useMediaQuery(queries.belowTablet)
  const film = compact ? FILMS.square : FILMS.landscape

  return (
    <section id="film" className="section film-section" aria-labelledby="film-title">
      <div className="container">
        <div className="film-section__head">
          <Reveal>
            <h2 id="film-title" className="h1">
              Thirty seconds. Four chapters.
            </h2>
          </Reveal>
          <Reveal delay={120}>
            <p className="lead">Commerce began with buying and selling. It moved online, then it got fast. Now it starts from the need itself.</p>
          </Reveal>
        </div>
        <div className="film-section__stage" style={{ aspectRatio: film.ratio }}>
          <FilmVideo key={film.src} src={film.src} poster={film.poster} reduced={reduced} />
        </div>
      </div>
    </section>
  )
}
