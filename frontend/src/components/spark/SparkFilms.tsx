import type { CSSProperties } from 'react'

const FILMS = {
  intro: {
    title: 'Meet Spark',
    kicker: 'The introduction',
    description:
      'How Parts Intelligence connects machines, parts, suppliers and stock, and where the evidence comes from.',
    src: '/parts-intelligence-intro.mp4',
    poster: '/parts-intelligence-intro.jpg',
    captions: null,
  },
  workflow: {
    title: 'From need to order',
    kicker: 'The workflow',
    description: 'One request, followed through fitment and supply to an order for your review.',
    src: '/agentic-workflow-film.mp4?v=20261029',
    poster: '/agentic-workflow-film.jpg?v=20261029',
    captions: '/agentic-workflow-film.vtt?v=20261029',
  },
  story: {
    title: 'The commerce story',
    kicker: 'The thinking',
    description: 'Why commerce is moving from searching a catalogue to starting with a need.',
    src: '/evolution-video.mp4?v=20261022',
    poster: '/evolution-video-poster.jpg',
    captions: null,
  },
} as const

/** One of the three Spark films, playable where it sits. */
export function SparkFilm({
  film,
  className = '',
  style,
}: {
  film: keyof typeof FILMS
  className?: string
  style?: CSSProperties
}) {
  const item = FILMS[film]
  return (
    <figure className={`sp-film ${className}`} style={style}>
      {/* Only the workflow film has a supplied, verified caption track. */}
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <video controls playsInline preload="none" poster={item.poster} aria-label={item.title}>
        <source src={item.src} type="video/mp4" />
        {item.captions ? (
          <track kind="captions" src={item.captions} srcLang="en" label="English" />
        ) : null}
        Your browser cannot play this film. <a href={item.src}>Download the film</a>.
      </video>
      <figcaption>
        <span>{item.kicker}</span>
        <strong>{item.title}</strong>
        <p>{item.description}</p>
      </figcaption>
    </figure>
  )
}
