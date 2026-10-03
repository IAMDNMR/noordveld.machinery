import { useEffect, useRef, useState } from 'react'
import type { Film } from '../../data/content'
import { useInView } from '../../hooks/useInView'
import { queries } from '../../lib/breakpoints'
import { useMediaQuery, useReducedMotion } from '../../hooks/useMediaQuery'
import { filmPosterUrl, videoUrl } from '../../lib/assets'
import { VideoPlaceholder } from './Placeholders'
import './media.css'

type Connection = { saveData?: boolean }

/** True when the visitor asked the browser to save data. Read once; it rarely changes mid-visit. */
const prefersSavedData = (): boolean => (navigator as Navigator & { connection?: Connection }).connection?.saveData === true

interface FilmSlotProps {
  film: Film
  /** Overrides the film's own ratio. Films are 16:9 natively, so other ratios crop the frame. */
  ratio?: string
  /** `hero` is the bare frame (the hero builds its own stage) and starts loading at once */
  size?: 'hero' | 'standard'
}

/**
 * A film from src/assets/videos, with fallbacks at every step:
 *  - no file                      → polished placeholder
 *  - reduced motion or Save-Data  → the poster frame only, nothing plays or downloads
 *  - phones                       → the smaller -mobile cut
 *  - video error                  → the poster frame
 * Otherwise it plays muted and looping while on screen and pauses when scrolled away.
 * The frame is smaller than its slot and feathered into the page on all four sides (no box edge). The feather,
 * a slight overscale and a stronger fade in the bottom-right corner keep the generator's corner mark out of sight.
 */
export function FilmSlot({ film, ratio, size = 'standard' }: FilmSlotProps) {
  const reduced = useReducedMotion()
  const compact = useMediaQuery(queries.belowTablet)
  const [saveData] = useState(prefersSavedData)

  const desktop = videoUrl(film.id)
  if (!desktop) return <VideoPlaceholder film={film} ratio={ratio} size={size} />

  const mobile = videoUrl(film.id, 'mobile')
  const poster = filmPosterUrl(film.id)
  const staticOnly = (reduced || saveData) && poster !== undefined
  const src = compact && mobile ? mobile : desktop

  return <FilmFrame key={staticOnly ? 'still' : src} film={film} src={src} poster={poster} ratio={ratio} hero={size === 'hero'} staticOnly={staticOnly} />
}

interface FilmFrameProps {
  film: Film
  src: string
  poster?: string
  ratio?: string
  hero: boolean
  staticOnly: boolean
}

function FilmFrame({ film, src, poster, ratio, hero, staticOnly }: FilmFrameProps) {
  const frameRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [failed, setFailed] = useState(false)
  // Below-the-fold films only start downloading when they are about to scroll into view
  const near = useInView(frameRef, { once: true, rootMargin: '500px 0px' })
  const visible = useInView(videoRef, { threshold: 0.25 })
  const style = { aspectRatio: ratio ?? film.ratio }

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (visible) void video.play().catch(() => undefined)
    else video.pause()
  }, [visible])

  const content =
    staticOnly || failed ? (
      <div ref={frameRef} className="film" style={style}>
        {poster ? <img className="film__video" src={poster} alt={film.title} loading={hero ? 'eager' : 'lazy'} decoding="async" /> : null}
      </div>
    ) : (
      <div ref={frameRef} className="film" style={style}>
        <video
          ref={videoRef}
          className="film__video"
          src={hero || near ? src : undefined}
          poster={poster}
          muted
          loop
          playsInline
          preload={hero ? 'auto' : 'metadata'}
          aria-label={film.title}
          onError={() => setFailed(true)}
        />
      </div>
    )

  // The hero supplies its own stage (see Hero.tsx); every other film gets a ghost word behind the frame
  if (hero) return content
  return (
    <div className="film-stage">
      <span className="film-stage__word" aria-hidden="true">
        {film.word}
      </span>
      {content}
    </div>
  )
}
