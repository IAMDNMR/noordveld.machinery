import type { Plant, PlantId } from '../types/catalog'

const W = 600
const H = 560
const LON = [6.3, 7.6] as const
const LAT = [52.35, 53.15] as const

const project = (lon: number, lat: number): [number, number] => [((lon - LON[0]) / (LON[1] - LON[0])) * W, ((LAT[1] - lat) / (LAT[1] - LAT[0])) * H]

/** Approximate border between the Netherlands and Germany, drawn as a dashed line. */
const border: [number, number][] = [
  [7.02, 53.15],
  [7.0, 52.95],
  [6.93, 52.78],
  [6.9, 52.62],
  [6.97, 52.5],
  [7.03, 52.35],
]

const gridLon = [6.5, 6.75, 7.0, 7.25, 7.5]
const gridLat = [52.5, 52.75, 53.0]

interface PlantMapProps {
  plants: readonly Plant[]
  active: PlantId
  onSelect: (id: PlantId) => void
}

/** Schematic regional map: no map API, positions placed from approximate coordinates. */
export function PlantMap({ plants: all, active, onSelect }: PlantMapProps) {
  const plants = all.filter((p): p is Plant & { lat: number; lon: number } => p.lat !== null && p.lon !== null)
  const westmost = plants.reduce<string | null>((w, p) => (w === null || p.lon < (plants.find((x) => x.id === w)?.lon ?? Infinity) ? p.id : w), null)
  const route = [...plants].sort((a, b) => b.lat - a.lat)
  const borderPath = border.map(([lon, lat], i) => `${i === 0 ? 'M' : 'L'}${project(lon, lat).join(' ')}`).join(' ')
  return (
    <figure className="pmap">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Schematic map showing the plants at ${plants.map((p) => p.city).join(', ')}`}>
        {gridLon.map((lon) => (
          <line key={lon} x1={project(lon, 0)[0]} x2={project(lon, 0)[0]} y1={0} y2={H} className="pmap__grid" />
        ))}
        {gridLat.map((lat) => (
          <line key={lat} x1={0} x2={W} y1={project(0, lat)[1]} y2={project(0, lat)[1]} className="pmap__grid" />
        ))}
        <path d={borderPath} className="pmap__border" />
        <text x={project(6.62, 0)[0] - 90} y={34} className="pmap__country">
          Netherlands
        </text>
        <text x={project(7.3, 0)[0]} y={34} className="pmap__country">
          Germany
        </text>

        {route.length > 1 ? <path d={route.map((p, i) => `${i ? 'L' : 'M'}${project(p.lon, p.lat).join(' ')}`).join(' ')} className="pmap__link" /> : null}

        {plants.map((plant) => {
          const [x, y] = project(plant.lon, plant.lat)
          const on = plant.id === active
          const labelRight = plant.id !== westmost
          return (
            <g key={plant.id} className={`pmap__plant ${on ? 'is-active' : ''}`} onPointerEnter={() => onSelect(plant.id)} onClick={() => onSelect(plant.id)}>
              <circle cx={x} cy={y} r={on ? 26 : 18} className="pmap__halo" />
              <circle cx={x} cy={y} r={7} className="pmap__dot" />
              <text x={x + (labelRight ? 22 : 22)} y={y - 8} className="pmap__city">
                {plant.city}
              </text>
              <text x={x + 22} y={y + 14} className="pmap__brand">
                {plant.brand}
              </text>
            </g>
          )
        })}
      </svg>
      <figcaption>Schematic map, not to scale.</figcaption>
    </figure>
  )
}
