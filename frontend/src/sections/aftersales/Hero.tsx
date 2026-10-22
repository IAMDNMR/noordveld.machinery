import { RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import type { PartSummary } from '../../api'
import { ButtonLink } from '../../components/ButtonLink'
import { useInView } from '../../hooks/useInView'
import { useMediaQuery, useReducedMotion } from '../../hooks/useMediaQuery'
import { filmPosterUrl, machineImageUrl, partImageUrl, videoUrl } from '../../lib/assets'
import { partPath } from '../../lib/storeQuery'
import annotation from '../../assets/machines/nv-4500/hotspots.json'
import { label, sentence } from './data'

/*
  The machine-to-part sequence. A pure function of time t (seconds since the hero came into view), so it can be replayed and is fully shown at once for reduced motion.
    0.0 – 3.6   the machine at work (the site's hero film), headline in
    3.6 – 4.6   the film gives way to the still machine; slow push-in continues
    4.6 – 6.4   a scan line crosses the machine; each component it passes is marked and named
    6.6 – 8.6   exploded view: each marked component lifts out of the machine onto its own plate, tied back by a line
    8.8 – 10.4  one component comes into focus with its catalogue record
   10.4 – 12.0  machine → part → fitment → Parts Intelligence
  The headline and both actions are on screen from the first frame; nothing waits for the sequence.
*/
const END = 12.2

const slug = 'nv-4500'
const IMAGE_RATIO = 1376 / 768

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
const ease = (v: number) => 1 - Math.pow(1 - clamp01(v), 3)
const seg = (t: number, a: number, b: number) => ease((t - a) / (b - a))

function useSequence(start: boolean, reduced: boolean): [number, () => void] {
  const [t, setT] = useState(reduced ? END : 0)
  const [run, setRun] = useState(0)
  useEffect(() => {
    if (!start || reduced) return
    let raf = 0
    let last = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      const v = Math.min(END, (now - t0) / 1000)
      if (now - last > 30 || v >= END) {
        last = now
        setT(v)
      }
      if (v < END) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `run` restarts the sequence (replay)
  }, [start, reduced, run])
  return [reduced ? END : t, () => { setT(0); setRun((n) => n + 1) }]
}

export function AftersalesHero({ parts }: { parts: PartSummary[] | null }) {
  const root = useRef<HTMLElement>(null)
  const inView = useInView(root, { once: true, threshold: 0.2 })
  const reduced = useReducedMotion()
  const compact = useMediaQuery('(max-width: 900px)')
  const [t, replay] = useSequence(inView, reduced)

  // a component is shown only when the catalogue confirms it fits the annotated machine
  const spots = useMemo(() => {
    if (!annotation || !parts) return []
    return annotation.hotspots
      .map((h) => ({ ...h, record: parts.find((p) => p.part_number === h.part && p.fitment.some((f) => f.model_code === annotation.machine)) }))
      .filter((h): h is typeof h & { record: PartSummary } => Boolean(h.record))
  }, [parts])
  const focus = spots.find((s) => s.id === annotation?.focus) ?? spots[0]
  const still = slug ? machineImageUrl(slug) : undefined
  const film = videoUrl('hero', compact ? 'mobile' : 'desktop')
  const poster = filmPosterUrl('hero')

  const filmOut = seg(t, 3.6, 4.6)
  const scan = (t - 4.6) / 1.8 // scan position across the stage, 0 → 1
  const explode = seg(t, 6.6, 8.6)
  const focusIn = seg(t, 8.8, 9.8)
  const chain = seg(t, 10.4, 11.8)
  const push = 1.07 - 0.07 * clamp01(t / END)
  const plateSlots = spots.length

  return (
    <section ref={root} className="as-hero on-dark" aria-labelledby="as-hero-title">
      {film && !reduced ? (
        <video className="as-hero__film" src={film} poster={poster} autoPlay muted loop playsInline aria-hidden="true" style={{ opacity: 1 - filmOut, transform: `scale(${1.04 + 0.06 * clamp01(t / 4.6)})` }} />
      ) : null}
      <div className="as-hero__grid" aria-hidden="true" style={{ opacity: 0.25 + 0.5 * filmOut }} />
      <div className="as-hero__shade" aria-hidden="true" />

      <div className="container as-hero__copy">
        <p className="label as-hero__eyebrow">After-sales · Parts &amp; Services</p>
        <h1 id="as-hero-title" className="as-hero__title">
          <span style={{ animationDelay: '80ms' }}>Every Machine Has a Story.</span> <span className="accent" style={{ animationDelay: '380ms' }}>Keep It Moving.</span>
        </h1>
        <p className="lead as-hero__lead">Find the right parts, understand machine compatibility, explore technical relationships, and connect every order to the service journey.</p>
        <div className="as-hero__actions">
          <ButtonLink to="/parts-store">Explore Parts</ButtonLink>
          <ButtonLink to="#find-parts" variant="secondary" arrow={false} external>
            Find the Right Part
          </ButtonLink>
        </div>
        {t >= END && !reduced ? (
          <button type="button" className="as-hero__replay" onClick={replay}>
            <RotateCcw size={16} aria-hidden="true" /> Replay the sequence
          </button>
        ) : null}
      </div>

      {still && annotation ? (
        <div className="as-stage" style={{ '--ratio': IMAGE_RATIO, opacity: reduced ? 1 : filmOut } as CSSProperties} aria-label={`Components of the ${annotation.machine} with their catalogue records`} role="img">
          <img className="as-stage__machine" src={still} alt="" style={{ transform: `scale(${push})`, filter: `brightness(${0.78 - 0.3 * explode}) saturate(${0.85 - 0.3 * explode})` }} />
          {/* the scan */}
          {scan > 0 && scan < 1.08 ? <i className="as-stage__scan" style={{ left: `${Math.min(1, scan) * 100}%`, opacity: 1 - seg(t, 6.2, 6.6) }} /> : null}
          <svg className="as-stage__lines" viewBox="0 0 1000 558" preserveAspectRatio="none" aria-hidden="true">
            {spots.map((s, i) => {
              const target = plateCentre(i, plateSlots, compact)
              const p = clamp01((explode - i * 0.08) / 0.7)
              if (p <= 0 || compact) return null
              const x1 = s.x * 1000
              const y1 = s.y * 558
              const x2 = x1 + (target.x * 1000 - x1) * p
              const y2 = y1 + (target.y * 558 - y1) * p
              return <line key={s.id} x1={x1} y1={y1} x2={x2} y2={y2} className={s.id === focus?.id && focusIn > 0 ? 'is-focus' : ''} />
            })}
            {/* measurement ticks along the scan path */}
            {Array.from({ length: 21 }, (_, i) => <line key={`tick-${i}`} x1={i * 50} y1={548} x2={i * 50} y2={i % 5 === 0 ? 532 : 540} className="tick" style={{ opacity: seg(t, 4.6 + i * 0.05, 5.0 + i * 0.05) * 0.6 }} />)}
          </svg>

          {spots.map((s) => {
            const on = seg(t, 4.6 + s.x * 1.8, 5.0 + s.x * 1.8)
            return (
              <div key={s.id} className={`as-spot ${s.id === focus?.id && focusIn > 0 ? 'is-focus' : ''}`} style={{ left: `${s.x * 100}%`, top: `${s.y * 100}%`, opacity: on }}>
                <i />
                <span className="as-spot__label" style={{ opacity: on * (1 - explode * 0.85) }}>{s.record.category ?? s.record.subcategory}</span>
              </div>
            )
          })}

          {!compact &&
            spots.map((s, i) => {
              const target = plateCentre(i, plateSlots, compact)
              const p = clamp01((explode - i * 0.08) / 0.7)
              const img = partImageUrl(s.record.part_number)
              const isFocus = s.id === focus?.id
              const x = s.x + (target.x - s.x) * p
              const y = s.y + (target.y - s.y) * p
              const dim = focusIn > 0 && !isFocus ? 1 - 0.45 * focusIn : 1
              return (
                <Link key={s.id} to={partPath(s.record.part_number)} className={`as-plate ${isFocus && focusIn > 0 ? 'is-focus' : ''}`} tabIndex={p > 0.9 ? 0 : -1} aria-hidden={p < 0.9}
                  style={{ left: `${x * 100}%`, top: `${y * 100}%`, opacity: Math.min(1, p * 1.6) * dim, transform: `translate(-50%, -50%) scale(${0.35 + 0.65 * p + (isFocus ? 0.12 * focusIn : 0)})` }}>
                  {img ? <img src={img} alt="" loading="lazy" /> : null}
                  <span className="as-plate__no">{s.record.part_number}</span>
                </Link>
              )
            })}

          {focus ? (
            <aside className="as-ident" style={{ opacity: focusIn, transform: `translateY(${(1 - focusIn) * 16}px)` }} aria-hidden={focusIn < 0.5}>
              <p className="as-ident__eyebrow">Component identified</p>
              <p className="as-ident__name">{focus.record.name}</p>
              <dl>
                <div><dt>Part number</dt><dd className="as-mono">{focus.record.part_number}</dd></div>
                <div><dt>Category</dt><dd>{focus.record.category}{focus.record.subcategory ? ` · ${focus.record.subcategory}` : ''}</dd></div>
                <div><dt>Recorded fitment</dt><dd>{focus.record.fitment.map((f) => `${f.model_code}${f.fitment_status ? ` (${label(f.fitment_status)})` : ''}`).join(', ')}</dd></div>
              </dl>
              <Link className="as-ident__link" to={partPath(focus.record.part_number)} tabIndex={focusIn > 0.5 ? 0 : -1}>View the part →</Link>
            </aside>
          ) : null}

          <ol className="as-chain" style={{ opacity: chain }} aria-hidden={chain < 0.5}>
            {['Machine', 'Part', 'Fitment', 'Parts Intelligence'].map((n, i) => (
              <li key={n} style={{ opacity: seg(t, 10.4 + i * 0.3, 10.9 + i * 0.3) }}>
                <span>{n}</span>
                <em>{i === 0 ? annotation.machine : i === 1 ? focus?.record.part_number : i === 2 ? sentence(focus?.record.fitment.find((f) => f.model_code === annotation.machine)?.fitment_status) : 'evidence-led answers'}</em>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  )
}

/** Where each component's plate settles in the exploded view: a row above the machine, inside the stage (fractions of the stage). */
function plateCentre(i: number, n: number, compact: boolean): { x: number; y: number } {
  if (compact) return { x: 0.5, y: 0.5 }
  const span = 0.62
  const x = 0.22 + (n <= 1 ? span / 2 : (i / (n - 1)) * span)
  return { x, y: 0.15 + (i % 2) * 0.07 }
}
