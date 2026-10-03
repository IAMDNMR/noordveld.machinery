import { Play } from 'lucide-react'
import type { Film } from '../../data/content'
import './media.css'

/** Append ?placeholders to any URL to see each slot's intended asset path on screen. */
const showSpec = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('placeholders')

export type ImageType = 'studio' | 'action' | 'detail'

interface MachineImagePlaceholderProps {
  model: string
  /** CSS aspect-ratio, e.g. "4 / 3" */
  ratio: string
  imageType: ImageType
  alt: string
  /** Where the final image should be placed */
  assetPath: string
}

/**
 * Stands in for a machine image: a studio-lit frame with the model mark.
 * Replace by adding the file at `assetPath` (see src/assets/README.md); nothing else changes.
 */
export function MachineImagePlaceholder({ model, ratio, imageType, alt, assetPath }: MachineImagePlaceholderProps) {
  return (
    <div className="mimg__inner mimg__placeholder" style={{ aspectRatio: ratio }} role="img" aria-label={alt} data-image-type={imageType} data-asset-path={assetPath}>
      <span className="mimg__floor" aria-hidden="true" />
      <span className="mimg__crop mimg__crop--tl" aria-hidden="true" />
      <span className="mimg__crop mimg__crop--tr" aria-hidden="true" />
      <span className="mimg__crop mimg__crop--bl" aria-hidden="true" />
      <span className="mimg__crop mimg__crop--br" aria-hidden="true" />
      <span className="mimg__model" aria-hidden="true">
        {model}
      </span>
      {showSpec ? <span className="mimg__spec">{imageType} · {ratio} · {assetPath}</span> : null}
    </div>
  )
}

/** Viewfinder corner marks shared by the dark placeholders */
function Crops() {
  return (
    <>
      <span className="mimg__crop mimg__crop--tl" aria-hidden="true" />
      <span className="mimg__crop mimg__crop--tr" aria-hidden="true" />
      <span className="mimg__crop mimg__crop--bl" aria-hidden="true" />
      <span className="mimg__crop mimg__crop--br" aria-hidden="true" />
    </>
  )
}

interface PlantImagePlaceholderProps {
  city: string
  ratio: string
  alt: string
  assetPath: string
}

/** Stands in for a plant image: a low-light exterior frame with a horizon line. */
export function PlantImagePlaceholder({ city, ratio, alt, assetPath }: PlantImagePlaceholderProps) {
  return (
    <div className="pimg__inner" style={{ aspectRatio: ratio }} role="img" aria-label={alt} data-asset-path={assetPath}>
      <span className="pimg__horizon" aria-hidden="true" />
      <Crops />
      <span className="pimg__city" aria-hidden="true">
        {city}
      </span>
      {showSpec ? <span className="mimg__spec">{ratio} · {assetPath}</span> : null}
    </div>
  )
}

interface EditorialPlaceholderProps {
  /** What the final image shows, e.g. "Mechanical detail" */
  subject: string
  ratio: string
  alt: string
}

/** Stands in for brand and editorial photography (work environments, engineering, detail). */
export function EditorialPlaceholder({ subject, ratio, alt }: EditorialPlaceholderProps) {
  return (
    <div className="pimg__inner" style={{ aspectRatio: ratio }} role="img" aria-label={alt} data-subject={subject}>
      <span className="pimg__horizon" aria-hidden="true" />
      <Crops />
      <span className="pimg__city" aria-hidden="true">
        {subject}
      </span>
      {showSpec ? <span className="mimg__spec">{ratio} · {subject}</span> : null}
    </div>
  )
}

interface VideoPlaceholderProps {
  film: Film
  /** Overrides the film's own ratio */
  ratio?: string
  /** Compact variant for small slots */
  size?: 'hero' | 'standard'
}

/**
 * Stands in for a film: cinematic frame, soft moving light, play indicator and a clear label.
 * Never shows browser video controls.
 */
export function VideoPlaceholder({ film, ratio, size = 'standard' }: VideoPlaceholderProps) {
  return (
    <div className={`vph vph--${size}`} style={{ aspectRatio: ratio ?? film.ratio }} role="img" aria-label={`${film.title}: film coming soon`} data-film={film.id}>
      <span className="vph__light" aria-hidden="true" />
      <span className="vph__grain" aria-hidden="true" />
      <span className="vph__bars vph__bars--top" aria-hidden="true" />
      <span className="vph__bars vph__bars--bottom" aria-hidden="true" />
      <div className="vph__centre">
        <span className="vph__play" aria-hidden="true">
          <Play size={size === 'hero' ? 34 : 26} strokeWidth={1.6} fill="currentColor" />
        </span>
      </div>
      <div className="vph__meta">
        <span className="vph__title">{film.title}</span>
        <span className="vph__status">Film coming soon</span>
      </div>
      {showSpec ? <span className="mimg__spec">{film.id} · {ratio ?? film.ratio} · {film.brief}</span> : null}
    </div>
  )
}
