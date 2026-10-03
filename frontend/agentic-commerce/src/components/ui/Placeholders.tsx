import './placeholders.css'

/**
 * Intentional asset slots. The page is complete without them (every visual is code-drawn); each slot
 * is a backdrop layer that a generated image can later replace without touching layout.
 *
 * To replace a slot: render an <img> (or <picture>) with `className="asset-fill"` inside the
 * placeholder instead of the gradient, using the dimensions below.
 * Append `?placeholders` to the page URL to see each slot's label and spec on screen.
 */
export type VisualPlaceholderType = 'commerce' | 'quick-commerce' | 'agentic-commerce'

interface AssetSpec {
  purpose: string
  size: string
  aspect: string
  direction: string
  usedIn: string
}

export const assetSpecs: Record<VisualPlaceholderType, AssetSpec> = {
  commerce: {
    purpose: 'Physical-world backdrop for stage 01. A tabletop surface with soft raking light.',
    size: '1600 × 1000 px',
    aspect: '16:10',
    direction: 'Warm paper/stone surface, long soft shadows, minimal, editorial. No people, no logos.',
    usedIn: 'Evolution section, stage 01 scene.',
  },
  'quick-commerce': {
    purpose: 'Spatial backdrop for stage 03. A top-down abstract map with depth falloff.',
    size: '1600 × 1000 px',
    aspect: '16:10',
    direction: 'Light neutral topography/grid, subtle radial depth, blue only as a sparse accent. No literal city map.',
    usedIn: 'Evolution section, stage 03 scene.',
  },
  'agentic-commerce': {
    purpose: 'Depth backdrop for stage 04. Soft volumetric light suggesting understanding.',
    size: '1600 × 1000 px',
    aspect: '16:10',
    direction: 'Graphite-to-warm-white gradient volume, faint structural lines, one blue source. No HUD, no brain, no chat bubbles.',
    usedIn: 'Evolution section, stage 04 scene.',
  },
}

const showLabels = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('placeholders')

export function VisualPlaceholder({ type }: { type: VisualPlaceholderType }) {
  const spec = assetSpecs[type]
  return (
    <div
      className={`placeholder placeholder--${type}`}
      aria-hidden="true"
      data-asset={type}
      data-asset-size={spec.size}
      data-asset-aspect={spec.aspect}
      data-asset-direction={spec.direction}
      data-asset-used-in={spec.usedIn}
    >
      {showLabels ? (
        <span className="placeholder__spec">
          <strong>{type}</strong> · {spec.size} · {spec.aspect}
          <br />
          {spec.purpose}
        </span>
      ) : null}
    </div>
  )
}
