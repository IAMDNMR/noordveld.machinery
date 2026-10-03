import { CircleCheck } from 'lucide-react'
import type { ComponentType, ReactNode } from 'react'
import { AbsoluteFill } from 'remotion'
import { AgenticScene } from '../components/scenes/AgenticScene'
import { CommerceScene } from '../components/scenes/CommerceScene'
import { EcommerceScene } from '../components/scenes/EcommerceScene'
import { Glyph } from '../components/scenes/primitives'
import { QuickScene } from '../components/scenes/QuickScene'
import { clamp01, easeInOut, easeOut, lerp, linear, seg } from '../lib/math'
import type { StageId } from '../data/stages'
import { CROSSFADE, FILM_SECONDS, OUTCOME_START, acts, layoutFor, type FilmFormat } from './timeline'

const scenes: Record<StageId, ComponentType<{ p: number }>> = {
  commerce: CommerceScene,
  'e-commerce': EcommerceScene,
  'quick-commerce': QuickScene,
  'agentic-e-commerce': AgenticScene,
}

const font = 'var(--font-sans)'
const RAIL = ['Commerce', 'E-Commerce', 'Quick Commerce', 'Agentic E-Commerce'] as const

interface EvolutionFilmProps {
  /** Time in seconds. The composition is a pure function of this value, so any frame can be rendered. */
  time: number
  format?: FilmFormat
}

/** In-and-out visibility of a window [start, end] with soft edges. */
const window01 = (t: number, start: number, end: number, fade = CROSSFADE): number => Math.min(seg(t, start, start + fade, linear), 1 - seg(t, end - fade, end, linear))

/** Soft teal light that drifts across the stage as the story moves from the physical to the intelligent. */
function Light({ t, width, height }: { t: number; width: number; height: number }) {
  const progress = clamp01(t / OUTCOME_START)
  const cx = lerp(0.2, 0.78, easeInOut(progress)) * width
  const cy = lerp(0.7, 0.38, easeInOut(progress)) * height
  return (
    <>
      <defs>
        <radialGradient id="film-light" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#00bfa5" stopOpacity={0.2} />
          <stop offset="1" stopColor="#00bfa5" stopOpacity={0} />
        </radialGradient>
      </defs>
      <circle cx={cx} cy={cy} r={Math.max(width, height) * 0.55} fill="url(#film-light)" opacity={1 - seg(t, OUTCOME_START - 1, OUTCOME_START + 0.5, linear)} />
      <circle cx={width / 2} cy={height * 0.42} r={Math.max(width, height) * 0.5} fill="url(#film-light)" opacity={seg(t, OUTCOME_START + 0.2, OUTCOME_START + 2.4, linear)} />
    </>
  )
}

export function EvolutionFilm({ time, format = 'landscape' }: EvolutionFilmProps): ReactNode {
  const t = Math.min(Math.max(time, 0), FILM_SECONDS)
  const L = layoutFor(format)

  return (
    <AbsoluteFill style={{ background: 'var(--paper)', overflow: 'hidden' }}>
      <svg viewBox={`0 0 ${L.width} ${L.height}`} width="100%" height="100%" role="img" aria-label="Motion film: commerce, e-commerce, quick commerce and agentic e-commerce." style={{ display: 'block' }}>
        <Light t={t} width={L.width} height={L.height} />

        {acts.map((act) => {
          const Scene = scenes[act.id]
          const a = window01(t, act.start, act.end)
          const sceneP = seg(t, act.scene[0], act.scene[1], linear)
          const textA = window01(t, act.start + 0.25, act.end - 0.1, 0.7)
          const rise = (1 - easeOut(clamp01((t - act.start - 0.25) / 0.9))) * 26
          // Slow push-in across the act
          const zoom = lerp(1.05, 1, linear(clamp01((t - act.start) / (act.end - act.start))))
          const cx = L.scene.x + L.scene.w / 2
          const cy = L.scene.y + L.scene.h / 2
          return (
            <g key={act.id}>
              {a > 0.002 ? (
                <g transform={`translate(${cx} ${cy}) scale(${zoom}) translate(${-cx} ${-cy})`}>
                  <svg x={L.scene.x} y={L.scene.y} width={L.scene.w} height={L.scene.h} viewBox="0 0 800 500" opacity={a} style={{ overflow: 'visible' }}>
                    <Scene p={sceneP} />
                  </svg>
                </g>
              ) : null}
              {textA > 0.002 ? (
                <g opacity={textA} transform={`translate(0 ${rise})`}>
                  <text x={L.text.x} y={L.text.y - L.text.leading * 0.95} style={{ fontFamily: font, fontSize: L.text.kicker, fontWeight: 600, letterSpacing: '0.18em', fill: 'var(--accent-ink)' }}>
                    {act.kicker}
                  </text>
                  {act.lines.map((line, i) => (
                    <text key={line} x={L.text.x} y={L.text.y + i * L.text.leading} style={{ fontFamily: font, fontSize: L.text.line, fontWeight: 600, letterSpacing: '-0.04em', fill: 'var(--ink)' }}>
                      {line}
                    </text>
                  ))}
                </g>
              ) : null}
            </g>
          )
        })}

        <g opacity={1 - seg(t, OUTCOME_START - 0.6, OUTCOME_START, linear)}>
          <line x1={L.rail.x} x2={L.rail.x + L.rail.w} y1={L.rail.y - 34} y2={L.rail.y - 34} stroke="var(--line)" strokeWidth={2} />
          <line x1={L.rail.x} x2={L.rail.x + L.rail.w * clamp01(t / OUTCOME_START)} y1={L.rail.y - 34} y2={L.rail.y - 34} stroke="var(--accent)" strokeWidth={3} />
          {RAIL.map((name, i) => {
            const act = acts[i]
            const on = t >= act.start && t < act.end
            if (format !== 'landscape' && !on) return null
            return (
              <text key={name} x={L.rail.x + (L.rail.w * act.start) / OUTCOME_START} y={L.rail.y} style={{ fontFamily: font, fontSize: L.rail.font, fontWeight: 600, fill: on ? 'var(--ink)' : 'var(--ink-3)' }}>
                {name}
              </text>
            )
          })}
        </g>

        {t >= OUTCOME_START - 0.5 ? <Outcome t={t} L={L} /> : null}
      </svg>
    </AbsoluteFill>
  )
}

function Outcome({ t, L }: { t: number; L: ReturnType<typeof layoutFor> }) {
  const check = seg(t, OUTCOME_START + 0.3, OUTCOME_START + 1.3)
  const first = window01(t, OUTCOME_START + 1.0, FILM_SECONDS + 1, 1)
  const second = seg(t, OUTCOME_START + 2.0, OUTCOME_START + 3.0, linear)
  const name = seg(t, OUTCOME_START + 3.6, OUTCOME_START + 4.5, linear)
  const { x, y, line, leading } = L.outcome
  const style = { fontFamily: font, fontSize: line, fontWeight: 600, letterSpacing: '-0.045em', textAnchor: 'middle' } as const
  return (
    <g>
      <Glyph icon={CircleCheck} x={x} y={y - leading * 1.9} size={96} color="var(--accent)" opacity={check} scale={0.7 + 0.3 * check} strokeWidth={1.1} />
      <text x={x} y={y} opacity={first} style={{ ...style, fill: 'var(--ink)' }}>
        From buying what you know
      </text>
      <text x={x} y={y + leading + (1 - second) * 18} opacity={second} style={{ ...style, fill: 'var(--accent-ink)' }}>
        to solving what you need.
      </text>
      <text x={x} y={y + leading * 2.5 + (1 - name) * 14} opacity={name} style={{ fontFamily: font, fontSize: line * 0.38, fontWeight: 600, letterSpacing: '0.18em', textAnchor: 'middle', fill: 'var(--ink)' }}>
        AGENTIC E-COMMERCE
      </text>
    </g>
  )
}
