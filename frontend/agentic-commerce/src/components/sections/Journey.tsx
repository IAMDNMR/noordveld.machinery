import { useMemo, useRef } from 'react'
import { journey } from '../../data/process'
import { queries } from '../../lib/breakpoints'
import { clamp01 } from '../../lib/math'
import { useMediaQuery, useReducedMotion } from '../../hooks/useMediaQuery'
import { useScrollProgress } from '../../hooks/useScrollProgress'

type Pt = readonly [number, number]

interface Layout {
  width: number
  height: number
  points: Pt[]
  labelSide: (i: number) => 'above' | 'below' | 'right'
}

const SEGMENTS = journey.length - 1

function layoutFor(vertical: boolean): Layout {
  if (vertical) {
    const points = journey.map((_, i): Pt => [i % 2 === 0 ? 70 : 170, 50 + i * 78])
    return { width: 340, height: 50 + SEGMENTS * 78 + 40, points, labelSide: () => 'right' }
  }
  const points = journey.map((_, i): Pt => [60 + i * 110, [230, 150, 250, 160, 260, 170, 250, 180, 210][i]])
  return { width: 1000, height: 380, points, labelSide: (i) => (i % 2 === 0 ? 'below' : 'above') }
}

type Curve = readonly [Pt, Pt, Pt, Pt]

/** Smooth cubic segment between consecutive points (Catmull-Rom converted to Bézier). */
function segmentCurve(pts: readonly Pt[], i: number): Curve {
  const p0 = pts[Math.max(0, i - 1)]
  const p1 = pts[i]
  const p2 = pts[i + 1]
  const p3 = pts[Math.min(pts.length - 1, i + 2)]
  return [p1, [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6], [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6], p2]
}

const curvePath = ([a, b, c, d]: Curve): string => `M${a[0]} ${a[1]} C${b[0]} ${b[1]} ${c[0]} ${c[1]} ${d[0]} ${d[1]}`

const curvePoint = ([a, b, c, d]: Curve, t: number): Pt => {
  const u = 1 - t
  const w = [u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t]
  return [w[0] * a[0] + w[1] * b[0] + w[2] * c[0] + w[3] * d[0], w[0] * a[1] + w[1] * b[1] + w[2] * c[1] + w[3] * d[1]]
}

export function Journey() {
  const sectionRef = useRef<HTMLElement>(null)
  const vertical = useMediaQuery(queries.belowTablet)
  const reduced = useReducedMotion()
  const scrolled = useScrollProgress(sectionRef, !reduced)
  const progress = reduced ? 1 : clamp01(scrolled / 0.88)
  const layout = useMemo(() => layoutFor(vertical), [vertical])

  const travelled = progress * SEGMENTS
  const reached = Math.floor(travelled + 1e-6)

  const curves = useMemo(() => Array.from({ length: SEGMENTS }, (_, i) => segmentCurve(layout.points, i)), [layout])
  const dotCurve = Math.min(SEGMENTS - 1, Math.floor(travelled))
  const dot = curvePoint(curves[dotCurve], travelled - dotCurve)

  return (
    <section ref={sectionRef} className={`journey on-night ${reduced ? 'journey--static' : ''}`} aria-labelledby="journey-title">
      <div className="journey__sticky">
        <div className="container journey__inner">
          <header className="journey__head">
            <h2 id="journey-title" className="h2">
              From need to outcome, in one continuous motion.
            </h2>
            <p className="sr-only">The journey: {journey.map((j) => j.label).join(', then ')}.</p>
          </header>
          <svg className="journey__svg" viewBox={`0 0 ${layout.width} ${layout.height}`} aria-hidden="true" preserveAspectRatio="xMidYMid meet">
            {Array.from({ length: SEGMENTS }, (_, i) => {
              const d = curvePath(curves[i])
              const local = clamp01(travelled - i)
              return (
                <g key={i}>
                  <path d={d} className="journey__track" />
                  <path
                    d={d}
                    className="journey__trail"
                    pathLength={1}
                    strokeDasharray={`${local} 1.001`}
                  />
                </g>
              )
            })}
            {journey.map(({ label, icon: Icon }, i) => {
              const [x, y] = layout.points[i]
              const side = layout.labelSide(i)
              const on = i <= reached
              const last = i === journey.length - 1
              const tx = side === 'right' ? x + 40 : x
              const ty = side === 'right' ? y + 7 : side === 'above' ? y - 40 : y + 58
              return (
                <g key={label} className={`journey__node ${on ? 'is-on' : ''} ${last ? 'is-outcome' : ''}`}>
                  <circle cx={x} cy={y} r={last ? 28 : 24} />
                  <Icon x={x - 13} y={y - 13} size={26} strokeWidth={1.5} />
                  <text x={tx} y={ty} textAnchor={side === 'right' ? 'start' : 'middle'}>
                    {label}
                  </text>
                </g>
              )
            })}
            {progress > 0 && progress < 1 ? <circle cx={dot[0]} cy={dot[1]} r={8} className="journey__dot" /> : null}
          </svg>
        </div>
      </div>
    </section>
  )
}
