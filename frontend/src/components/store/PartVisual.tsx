import type { CSSProperties } from 'react'
import { iconFor, type StorePart } from '../../data/store'

const hash = (s: string): number => {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return h >>> 0
}

interface PartVisualProps {
  part: StorePart
  variant?: 'card' | 'large' | 'mini'
}

/**
 * The catalogue has no photographs yet, so each part gets a technical-drawing tile: the category's line icon over a
 * teal blueprint grid, with the part number. The glow position is derived from the part number, so tiles differ quietly.
 */
export function PartVisual({ part, variant = 'card' }: PartVisualProps) {
  const Icon = iconFor(part.category)
  const h = hash(part.no)
  const style = { '--gx': `${22 + (h % 56)}%`, '--gy': `${18 + ((h >> 8) % 44)}%` } as CSSProperties
  return (
    <div className={`pvis pvis--${variant}`} style={style} aria-hidden="true">
      <span className="pvis__cat">{part.category}</span>
      <Icon className="pvis__icon" strokeWidth={0.8} />
      <span className="pvis__no">{part.no}</span>
      <i className="pvis__mark pvis__mark--tl" />
      <i className="pvis__mark pvis__mark--tr" />
      <i className="pvis__mark pvis__mark--bl" />
      <i className="pvis__mark pvis__mark--br" />
    </div>
  )
}
