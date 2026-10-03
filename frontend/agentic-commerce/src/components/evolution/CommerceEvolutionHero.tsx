import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useMediaQuery, useReducedMotion } from '../../hooks/useMediaQuery'
import { useScrollProgress } from '../../hooks/useScrollProgress'
import { clamp01, seg } from '../../lib/math'
import logo from '../../../../src/assets/brand/logo.png'
import { FINALE_LINE, OPENING, STAGES, TOTAL } from './evolution-data'
import { EvolutionStage, makeLayout } from './EvolutionStage'
import './evolution.css'

/** Scroll length of the pinned hero, per breakpoint. The longer, the more dwell time each idea gets. */
const LENGTH = { desktop: 760, mobile: 640 } as const

function useStageSize(ref: React.RefObject<HTMLElement | null>) {
  const [size, setSize] = useState({ w: typeof window === 'undefined' ? 1280 : window.innerWidth, h: typeof window === 'undefined' ? 800 : window.innerHeight })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => setSize((s) => (s.w === el.clientWidth && s.h === el.clientHeight ? s : { w: el.clientWidth, h: el.clientHeight }))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return size
}

/** Scroll progress, eased: the film follows the scroll with a little weight instead of snapping to it. */
function useSmoothTime(ref: React.RefObject<HTMLElement | null>) {
  const raw = useScrollProgress(ref)
  const rawRef = useRef(0)
  rawRef.current = raw * TOTAL
  const [t, setT] = useState(0)
  const cur = useRef(0)
  const running = useRef(false)

  // On load (or refresh part-way down the page) land exactly where the scroll is: no replay from the start.
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const travel = rect.height - window.innerHeight
    const p = travel > 0 ? clamp01(-rect.top / travel) : 0
    cur.current = p * TOTAL
    setT(cur.current)
  }, [ref])

  useEffect(() => {
    if (running.current) return
    running.current = true
    let id = 0
    const tick = () => {
      const d = rawRef.current - cur.current
      if (Math.abs(d) < 0.003) {
        cur.current = rawRef.current
        setT(cur.current)
        running.current = false
        return
      }
      // fast scrolling is followed quickly, slow scrolling smoothly
      cur.current += d * Math.min(0.28, 0.1 + Math.abs(d) * 0.012)
      setT(cur.current)
      id = requestAnimationFrame(tick)
    }
    id = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(id)
      running.current = false
    }
  }, [raw])
  return t
}

function Pinned({ mobile }: { mobile: boolean }) {
  const section = useRef<HTMLElement>(null)
  const sticky = useRef<HTMLDivElement>(null)
  const t = useSmoothTime(section)
  const { w, h } = useStageSize(sticky)
  const layout = makeLayout(w, h, mobile)
  const cue = 1 - seg(t, 0.4, 3.2)

  return (
    <section id="top" ref={section} className="evo" style={{ height: `${mobile ? LENGTH.mobile : LENGTH.desktop}vh` }} aria-labelledby="evo-title">
      <h1 id="evo-title" className="sr-only">
        The evolution of commerce: Commerce, E-Commerce, Q-Commerce and Agentic Commerce
      </h1>
      <ol className="sr-only">
        {STAGES.map((s) => (
          <li key={s.id}>
            <h2>{s.title}</h2>
            <p>{s.statement}</p>
            <p>{s.summary}</p>
            <p>{s.flow.join(', then ')}.</p>
          </li>
        ))}
      </ol>
      <p className="sr-only">
        {OPENING.join(' ')} {FINALE_LINE}
      </p>
      <div ref={sticky} className="evo__sticky" aria-hidden="true">
        <EvolutionStage t={t} layout={layout} />
        <div className="evo-cue" style={{ opacity: cue }}>
          <span>Scroll</span>
          <i />
        </div>
      </div>
    </section>
  )
}

/** Reduced motion: no pinning, no scrubbing. The same four ideas, in order, with a quiet reveal. */
function Static() {
  return (
    <section id="top" className="evo-static" aria-labelledby="evo-title">
      <div className="container">
        <h1 id="evo-title" className="evo-static__head">
          <span>{OPENING[0]}</span> <em>{OPENING[1]}</em>
        </h1>
        <ol className="evo-static__list">
          {STAGES.map((s) => (
            <li key={s.id} className={`evo-static__item ${s.id === 'agentic-commerce' ? 'is-agentic' : ''}`}>
              <h2>{s.title}</h2>
              <p className="evo-static__statement">{s.statement}</p>
              <p className="evo-static__flow">{s.flow.join('  →  ')}</p>
              <p className="evo-static__summary">{s.summary}</p>
            </li>
          ))}
        </ol>
        <p className="evo-static__final">{FINALE_LINE}</p>
        <img className="evo-static__logo" src={logo} alt="Noordveld Machinery B.V." height={44} />
      </div>
    </section>
  )
}

export function CommerceEvolutionHero() {
  const reduced = useReducedMotion()
  const mobile = useMediaQuery('(max-width: 719px)')
  return reduced ? <Static /> : <Pinned mobile={mobile} />
}
