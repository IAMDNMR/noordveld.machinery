import { Cog } from 'lucide-react'
import type { CSSProperties } from 'react'
import { partImageUrl } from '../../lib/assets'

const hash = (s: string): number => {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return h >>> 0
}

interface PartImageProps {
  partNumber: string
  /** Shown on the placeholder only */
  category?: string | null
  /** Alt text for a real photo. The placeholder is decorative: the part's name is always next to it. */
  name: string
  variant?: 'card' | 'large' | 'mini'
}

/**
 * The one component that shows a part picture. It asks lib/assets for a photo by part number; when there is none it
 * draws the Noordveld placeholder: the same tile for every part, so a missing photo never looks like a broken one.
 */
export function PartImage({ partNumber, category, name, variant = 'card' }: PartImageProps) {
  const url = partImageUrl(partNumber)
  if (url) {
    return (
      <div className={`pimg pimg--${variant}`}>
        <img src={url} alt={variant === 'mini' ? '' : name} loading={variant === 'large' ? 'eager' : 'lazy'} decoding="async" />
      </div>
    )
  }
  const h = hash(partNumber)
  const style = { '--gx': `${22 + (h % 56)}%`, '--gy': `${18 + ((h >> 8) % 44)}%` } as CSSProperties
  return (
    <div className={`pvis pvis--${variant}`} style={style} role="img" aria-label={`No photo yet for ${name}`} data-placeholder="true">
      {category ? <span className="pvis__cat">{category}</span> : null}
      <Cog className="pvis__icon" strokeWidth={0.8} aria-hidden="true" />
      <span className="pvis__no">{partNumber}</span>
      <span className="pvis__soon">Photo to follow</span>
      <i className="pvis__mark pvis__mark--tl" />
      <i className="pvis__mark pvis__mark--bl" />
    </div>
  )
}
