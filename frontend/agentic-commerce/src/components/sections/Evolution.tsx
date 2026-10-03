import { useRef, type ComponentType } from 'react'
import { useReducedMotion } from '../../hooks/useMediaQuery'
import { useScrollProgress } from '../../hooks/useScrollProgress'
import { clamp01 } from '../../lib/math'
import { stages, type StageId } from '../../data/stages'
import { NoBreakName } from '../ui/NoBreakName'
import { VisualPlaceholder, type VisualPlaceholderType } from '../ui/Placeholders'
import { AgenticScene } from '../scenes/AgenticScene'
import { CommerceScene } from '../scenes/CommerceScene'
import { EcommerceScene } from '../scenes/EcommerceScene'
import { QuickScene } from '../scenes/QuickScene'
import './evolution.css'

const scenes: Record<StageId, ComponentType<{ p: number }>> = {
  commerce: CommerceScene,
  'e-commerce': EcommerceScene,
  'quick-commerce': QuickScene,
  'agentic-e-commerce': AgenticScene,
}
const backdrops: Partial<Record<StageId, VisualPlaceholderType>> = {
  commerce: 'commerce',
  'quick-commerce': 'quick-commerce',
  'agentic-e-commerce': 'agentic-commerce',
}

/** Share of the scroll each chapter gets. The commerce journey (cursor, clicks, delivery) is the longest, so it plays at a calm pace. */
const SPAN = [2.2, 1, 1, 1] as const
const SPAN_TOTAL = SPAN.reduce((a, b) => a + b, 0)

/** Scroll progress (0–1) → chapter position `g` (0–4, whole numbers are chapter starts). */
const toChapter = (progress: number): number => {
  let rest = progress * SPAN_TOTAL
  for (let i = 0; i < SPAN.length; i++) {
    if (rest <= SPAN[i]) return i + rest / SPAN[i]
    rest -= SPAN[i]
  }
  return SPAN.length
}

/** Visibility of chapter `i` for position `g` (0–4): full through the middle, short crossfade at the edges. */
const weight = (g: number, i: number): number => clamp01(1 - (Math.abs(g - (i + 0.5)) - 0.36) / 0.14)
/** Scene progress: the animation completes before the crossfade begins. */
const sceneProgress = (g: number, i: number): number => clamp01((g - i - 0.04) / 0.76)

export function Evolution() {
  const ref = useRef<HTMLElement>(null)
  const reduced = useReducedMotion()
  const progress = useScrollProgress(ref)
  const g = toChapter(progress)
  const active = Math.min(stages.length - 1, Math.floor(g))

  return (
    <section id="evolution" ref={ref} className="evolution" style={{ ['--span' as string]: SPAN_TOTAL }} aria-labelledby="evolution-title">
      <h2 id="evolution-title" className="sr-only">
        The evolution of commerce
      </h2>
      <ol className="sr-only">
        {stages.map((s) => (
          <li key={s.id}>
            <h3>{s.name}</h3>
            <p>{s.idea}</p>
            <p>{s.summary}</p>
            <p>{s.flow.join(', then ')}.</p>
          </li>
        ))}
      </ol>

      <div className="evolution__sticky">
        <div className="evolution__stage container" aria-hidden="true">
          <div className="evolution__copy">
            {stages.map((s, i) => {
              const w = reduced ? (i === active ? 1 : 0) : weight(g, i)
              return (
                <div key={s.id} className="evolution__text" style={{ opacity: w, transform: reduced ? undefined : `translateY(${(1 - w) * 24}px)`, visibility: w > 0.01 ? 'visible' : 'hidden' }}>
                  <h3 className="evolution__name h1"><NoBreakName name={s.name} /></h3>
                  <p className="evolution__idea">{s.idea}</p>
                  <p className="evolution__summary">{s.summary}</p>
                </div>
              )
            })}
          </div>

          <div className="evolution__visual">
            {stages.map((s, i) => {
              const w = reduced ? (i === active ? 1 : 0) : weight(g, i)
              if (w < 0.01) return null
              const Scene = scenes[s.id]
              const backdrop = backdrops[s.id]
              return (
                <div key={s.id} className="evolution__scene" style={{ opacity: w, transform: reduced ? undefined : `scale(${0.97 + 0.03 * w})` }}>
                  {backdrop ? <VisualPlaceholder type={backdrop} /> : null}
                  <Scene p={reduced ? 1 : sceneProgress(g, i)} />
                </div>
              )
            })}
          </div>
        </div>

      </div>

    </section>
  )
}
