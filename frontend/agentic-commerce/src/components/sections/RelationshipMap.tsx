import { relationNodes } from '../../data/process'

const COLS = [100, 300, 500] as const
const ROWS = [110, 290, 470] as const
/** Snake path through the nine relationships so each hand-off reads as one continuous chain. */
const POSITIONS: readonly (readonly [number, number])[] = [
  [COLS[0], ROWS[0]], [COLS[1], ROWS[0]], [COLS[2], ROWS[0]],
  [COLS[2], ROWS[1]], [COLS[1], ROWS[1]], [COLS[0], ROWS[1]],
  [COLS[0], ROWS[2]], [COLS[1], ROWS[2]], [COLS[2], ROWS[2]],
]

/** Labels sit above their node, except where a vertical connector would run through them. */
const labelPlacement: Record<string, { dx: number; dy: number; anchor: 'start' | 'middle' }> = {
  part: { dx: 40, dy: 7, anchor: 'start' },
  supplier: { dx: 0, dy: 62, anchor: 'middle' },
}
const defaultPlacement = { dx: 0, dy: -42, anchor: 'middle' } as const

interface RelationshipMapProps {
  /** Index of the active process step. */
  step: number
  stepCount: number
}

export function RelationshipMap({ step, stepCount }: RelationshipMapProps) {
  const lit = relationNodes.map((n) => step >= n.litAt)
  const fresh = relationNodes.map((n) => step === n.litAt)
  const acting = step === stepCount - 1

  return (
    <svg className="relmap" viewBox="0 0 600 560" role="img" aria-label="Relationships between machine, model, assembly, part, compatibility, alternative, supplier, inventory and location, lighting up as the requirement is worked through.">
      {POSITIONS.slice(0, -1).map(([x, y], i) => {
        const [x2, y2] = POSITIONS[i + 1]
        const on = lit[i] && lit[i + 1]
        return <line key={i} x1={x} y1={y} x2={x2} y2={y2} className={`relmap__edge ${on ? 'is-on' : ''}`} />
      })}
      {relationNodes.map((n, i) => {
        const [x, y] = POSITIONS[i]
        const place = labelPlacement[n.id] ?? defaultPlacement
        return (
          <g key={n.id} className={`relmap__node ${lit[i] ? 'is-on' : ''} ${fresh[i] ? 'is-new' : ''}`}>
            <circle cx={x} cy={y} r={fresh[i] ? 30 : 26} />
            <n.icon x={x - 14} y={y - 14} size={28} strokeWidth={1.5} />
            <text x={x + place.dx} y={y + place.dy} textAnchor={place.anchor}>
              {n.label}
            </text>
          </g>
        )
      })}
      <text x={300} y={548} textAnchor="middle" className={`relmap__act ${acting ? 'is-on' : ''}`}>
        Purchase → Fulfilment → Delivery
      </text>
    </svg>
  )
}
