import { Maximize2, Minimize2, Pause, Play, RotateCcw, SkipBack, SkipForward, Volume2, VolumeX } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from 'react'
import { useReducedMotion } from '../../hooks/useMediaQuery'
import { Hook, Narration } from './acts0'
import { ActMachine, ActNeed, ActUnderstand } from './acts1'
import { ActPart, ActSourcing } from './acts2'
import { ActAgentic, ActReveal, ActService, ActTransaction } from './acts3'
import { fall, lerp } from './motion'
import { enableSound, playClick, playConfirm } from './sound'
import { CHAPTERS, CLICKS, DURATION, HOOK, POSTER_TIME, STORY, WORLD_H, WORLD_W, cameraAt } from './timeline'
import { Cursor, Ripples } from './ui'
import './launch.css'

/** In viewer time */
const CONFIRM_AT = 36.6 + HOOK

const fmt = (s: number): string => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
const actIndex = (t: number): number => CHAPTERS.reduce((idx, a, i) => (t >= a.start ? i : idx), 0)

/**
 * Everything on screen is a pure function of time, so the film can be paused, scrubbed and replayed at any instant.
 * `time` is viewer time; the story's acts run on story time, which starts after the hook.
 */
function World({ time }: { time: number }) {
  const t = time - HOOK
  const glow = Math.max(0, t) / STORY
  return (
    <div className="lf-world" style={{ width: WORLD_W, height: WORLD_H, opacity: fall(t, 47.1, 47.95) }}>
      <div className="lf-glow" style={{ left: `${lerp(14, 82, glow)}%`, top: `${lerp(78, 30, glow)}%` }} />
      <Hook t={time} />
      {t < 9.8 ? <ActNeed t={t} /> : null}
      {t > 6.9 && t < 9.7 ? <ActUnderstand t={t} /> : null}
      <ActMachine t={t} />
      <ActPart t={t} />
      <ActSourcing t={t} />
      <ActAgentic t={t} />
      <ActTransaction t={t} />
      <ActService t={t} />
      <ActReveal t={t} />
      <Narration t={t} />
      <Ripples t={t} />
      <Cursor t={t} />
    </div>
  )
}

export function LaunchFilm() {
  const reduced = useReducedMotion()
  const root = useRef<HTMLDivElement>(null)
  const frame = useRef<HTMLDivElement>(null)
  const tRef = useRef(reduced ? POSTER_TIME : 0)
  const userPaused = useRef(false)
  const idleTimer = useRef<number>(0)

  const [t, setT] = useState(tRef.current)
  const [playing, setPlaying] = useState(false)
  const [sound, setSound] = useState(false)
  const [full, setFull] = useState(false)
  const [awake, setAwake] = useState(true)
  const [size, setSize] = useState({ w: 1280, h: 720 })
  const soundRef = useRef(false)
  soundRef.current = sound

  const ended = t >= DURATION - 0.001
  const portrait = size.w / size.h < 1.2

  // Measure the frame so the world scales to fit
  useEffect(() => {
    const el = frame.current
    if (!el) return
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    setSize({ w: el.clientWidth, h: el.clientHeight })
    return () => ro.disconnect()
  }, [full])

  // The clock
  useEffect(() => {
    if (!playing) return
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      const prev = tRef.current
      const next = Math.min(DURATION, prev + dt)
      tRef.current = next
      if (soundRef.current) {
        for (const c of CLICKS) if (prev < c.t + HOOK && next >= c.t + HOOK) playClick()
        if (prev < CONFIRM_AT && next >= CONFIRM_AT) playConfirm()
      }
      setT(next)
      if (next >= DURATION) {
        setPlaying(false)
        return
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing])

  const seek = useCallback((to: number) => {
    const v = Math.min(DURATION, Math.max(0, to))
    tRef.current = v
    setT(v)
  }, [])

  const play = useCallback(() => {
    userPaused.current = false
    if (tRef.current >= DURATION - 0.05 || (reduced && tRef.current === POSTER_TIME)) seek(0)
    setPlaying(true)
  }, [reduced, seek])
  const pause = useCallback(() => {
    userPaused.current = true
    setPlaying(false)
  }, [])
  const toggle = () => (playing ? pause() : play())
  const replay = () => {
    seek(0)
    play()
  }
  const next = () => {
    const i = actIndex(tRef.current)
    seek(i < CHAPTERS.length - 1 ? CHAPTERS[i + 1].start : DURATION)
  }
  const prev = () => {
    const i = actIndex(tRef.current)
    seek(tRef.current - CHAPTERS[i].start > 1.5 || i === 0 ? CHAPTERS[i].start : CHAPTERS[i - 1].start)
  }

  // Autoplay when the film is on screen; pause when it leaves (unless the viewer paused it themselves)
  useEffect(() => {
    const el = root.current
    if (!el || reduced) return
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !userPaused.current && tRef.current < DURATION - 0.05) setPlaying(true)
        else if (!entry.isIntersecting) setPlaying(false)
      },
      { threshold: 0.55 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [reduced])

  // Controls fade when idle
  const wake = useCallback(() => {
    setAwake(true)
    window.clearTimeout(idleTimer.current)
    idleTimer.current = window.setTimeout(() => setAwake(false), 2600)
  }, [])
  useEffect(() => () => window.clearTimeout(idleTimer.current), [])
  useEffect(() => {
    if (!playing) {
      window.clearTimeout(idleTimer.current)
      setAwake(true)
    } else wake()
  }, [playing, wake])

  useEffect(() => {
    const onChange = () => setFull(document.fullscreenElement === root.current)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])
  const toggleFull = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void root.current?.requestFullscreen?.()
  }
  const toggleSound = () => {
    if (!sound) enableSound()
    setSound(!sound)
  }

  const onKey = (e: KeyboardEvent) => {
    if (e.target instanceof HTMLButtonElement && e.key === ' ') return
    if (e.key === ' ' || e.key === 'k') {
      e.preventDefault()
      toggle()
    } else if (e.key === 'ArrowRight') seek(tRef.current + 5)
    else if (e.key === 'ArrowLeft') seek(tRef.current - 5)
    else if (e.key === 'f') toggleFull()
    else if (e.key === 'm') toggleSound()
    wake()
  }

  // Scrubbing
  const track = useRef<HTMLDivElement>(null)
  const scrubTo = (e: PointerEvent) => {
    const r = track.current?.getBoundingClientRect()
    if (r) seek(((e.clientX - r.left) / r.width) * DURATION)
  }

  const cam = cameraAt(Math.max(0, t - HOOK), portrait)
  const k = portrait ? size.w / cam.w : Math.min(size.w / WORLD_W, size.h / WORLD_H)
  const worldStyle: CSSProperties = { transform: `translate(${size.w / 2}px, ${size.h / 2}px) scale(${k * cam.z}) translate(${-cam.cx}px, ${-cam.cy}px)` }
  const started = t > 0.05
  const act = CHAPTERS[actIndex(t)]

  return (
    <section id="evolution" className="launch" aria-labelledby="launch-title">
      <h2 id="launch-title" className="sr-only">
        Agentic Commerce, a film
      </h2>
      <p className="sr-only">
        A {DURATION}-second film. A customer says that their NV-4500 is down and they need a hydraulic hose. The system understands the need, matches the machine, identifies the compatible part, finds stock and a delivery route, prepares the order and continues into service. All data shown comes from the Noordveld demonstration dataset.
      </p>

      <div
        ref={root}
        className={`lf ${full ? 'is-full' : ''} ${awake || !playing ? 'is-awake' : ''}`}
        tabIndex={0}
        role="group"
        aria-roledescription="film player"
        aria-label="Agentic Commerce film"
        onKeyDown={onKey}
        onPointerMove={wake}
        onPointerDown={wake}
      >
        <div ref={frame} className="lf-frame" onClick={(e) => (e.target as HTMLElement).closest('button') || toggle()}>
          <div className="lf-stage" style={worldStyle} aria-hidden="true">
            <World time={t} />
          </div>
          {!playing && (!started || ended) ? (
            <button type="button" className="lf-big" onClick={ended ? replay : play} aria-label={ended ? 'Replay film' : 'Play film'}>
              {ended ? <RotateCcw size={30} strokeWidth={1.6} aria-hidden="true" /> : <Play size={30} strokeWidth={1.6} aria-hidden="true" />}
            </button>
          ) : null}
        </div>

        <div className="lf-bar">
          <button type="button" onClick={toggle} aria-label={playing ? 'Pause' : ended ? 'Replay' : 'Play'}>
            {playing ? <Pause size={20} aria-hidden="true" /> : ended ? <RotateCcw size={20} aria-hidden="true" /> : <Play size={20} aria-hidden="true" />}
          </button>
          <button type="button" onClick={prev} aria-label="Previous scene">
            <SkipBack size={18} aria-hidden="true" />
          </button>
          <button type="button" onClick={next} aria-label="Next scene">
            <SkipForward size={18} aria-hidden="true" />
          </button>
          <div
            ref={track}
            className="lf-track"
            role="slider"
            tabIndex={-1}
            aria-label="Film progress"
            aria-valuemin={0}
            aria-valuemax={DURATION}
            aria-valuenow={Math.round(t)}
            aria-valuetext={`${fmt(t)} of ${fmt(DURATION)}, ${act.name}`}
            onPointerDown={(e) => {
              e.currentTarget.setPointerCapture(e.pointerId)
              scrubTo(e)
            }}
            onPointerMove={(e) => e.buttons === 1 && scrubTo(e)}
          >
            <i className="lf-track__fill" style={{ width: `${(t / DURATION) * 100}%` }} />
            {CHAPTERS.slice(1).map((a) => (
              <b key={a.id} className="lf-track__tick" style={{ left: `${(a.start / DURATION) * 100}%` }} />
            ))}
            <i className="lf-track__knob" style={{ left: `${(t / DURATION) * 100}%` }} />
          </div>
          <span className="lf-time">
            {fmt(t)} <span>/ {fmt(DURATION)}</span>
          </span>
          <button type="button" onClick={replay} aria-label="Replay from the start">
            <RotateCcw size={18} aria-hidden="true" />
          </button>
          <button type="button" onClick={toggleSound} aria-label={sound ? 'Turn sound off' : 'Turn sound on'} aria-pressed={sound}>
            {sound ? <Volume2 size={18} aria-hidden="true" /> : <VolumeX size={18} aria-hidden="true" />}
          </button>
          <button type="button" onClick={toggleFull} aria-label={full ? 'Exit full screen' : 'Full screen'}>
            {full ? <Minimize2 size={18} aria-hidden="true" /> : <Maximize2 size={18} aria-hidden="true" />}
          </button>
        </div>
      </div>
    </section>
  )
}
