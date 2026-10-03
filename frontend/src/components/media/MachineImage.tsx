import { useRef } from 'react'
import { useInView } from '../../hooks/useInView'
import { editorialImageUrl, machineAssetPath, machineImageUrl, plantImageUrl, type MachineImageKind } from '../../lib/assets'
import type { Machine, Plant } from '../../types/catalog'
import { EditorialPlaceholder, MachineImagePlaceholder, PlantImagePlaceholder, type ImageType } from './Placeholders'
import './media.css'

interface MachineImageProps {
  machine: Machine
  ratio?: string
  kind?: MachineImageKind
  imageType?: ImageType
  /** Wipe-reveal as the image enters the viewport */
  reveal?: boolean
  revealDelay?: number
  /** Skip lazy loading for above-the-fold images */
  eager?: boolean
}

/** Shows the machine's image when one exists in src/assets/machines/<slug>/, otherwise its placeholder. */
export function MachineImage({ machine, ratio = '4 / 3', kind = 'main', imageType = 'studio', reveal = false, revealDelay = 0, eager = false }: MachineImageProps) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, threshold: 0.2 })
  const url = machineImageUrl(machine.slug, kind)
  const alt = `${machine.model} ${machine.name} by ${machine.brand}`
  return (
    <div ref={ref} className={`mimg ${reveal ? 'mimg--reveal' : ''} ${inView ? 'is-in' : ''}`} style={{ aspectRatio: ratio, ['--reveal-delay' as string]: `${revealDelay}ms` }}>
      {url ? (
        <img className="mimg__inner" src={url} alt={alt} loading={eager ? 'eager' : 'lazy'} decoding="async" />
      ) : (
        <MachineImagePlaceholder model={machine.model} ratio={ratio} imageType={imageType} alt={alt} assetPath={machineAssetPath(machine.slug, kind)} />
      )}
    </div>
  )
}

interface PlantImageProps {
  plant: Plant
  ratio?: string
}

export function PlantImage({ plant, ratio = '16 / 10' }: PlantImageProps) {
  const url = plantImageUrl(plant.id)
  const alt = `${plant.city} plant, ${plant.brand}`
  return (
    <div className="mimg" style={{ aspectRatio: ratio, background: 'var(--charcoal-2)' }}>
      {url ? <img className="mimg__inner" src={url} alt={alt} loading="lazy" decoding="async" /> : <PlantImagePlaceholder city={plant.city} ratio={ratio} alt={alt} assetPath={`src/assets/plants/${plant.id}.webp`} />}
    </div>
  )
}

interface EditorialImageProps {
  /** File name without extension in src/assets/editorial, e.g. "machinery-at-work" */
  name: string
  subject: string
  ratio: string
  alt: string
  /** CSS object-position: which part of a wide photo stays in a portrait or square slot */
  position?: string
}

/** Brand and editorial photography: the real image when src/assets/editorial/<name>.* exists, otherwise a placeholder. */
export function EditorialImage({ name, subject, ratio, alt, position = '50% 50%' }: EditorialImageProps) {
  const url = editorialImageUrl(name)
  return url ? (
    <div className="mimg" style={{ aspectRatio: ratio, background: 'var(--charcoal-2)' }}>
      <img className="mimg__inner" src={url} alt={alt} loading="lazy" decoding="async" style={{ objectPosition: position }} />
    </div>
  ) : (
    <EditorialPlaceholder subject={subject} ratio={ratio} alt={alt} />
  )
}
