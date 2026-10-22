import mark from '../assets/brand/mark.png'

/** The existing Noordveld N, shared across Studio entry points. */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <img
      src={mark}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      decoding="async"
      style={{ display: 'block', objectFit: 'contain', flexShrink: 0 }}
    />
  )
}
