import { Check, Cog } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { clamp01, easeInOut, lerp, seg } from '../../lib/math'
import { spring } from '../launch/motion'
import logo from '../../../../src/assets/brand/logo.png'
import { AGENTIC_LINES, FINALE_LINE, FINALE_NAMES, MORPHS, NODES, OPENING, QUESTION, STAGES, T } from './evolution-data'

/* ───────── Layout ───────── */

const NAV = 72

export interface Layout {
  w: number
  h: number
  mobile: boolean
  gut: number
  node: (i: number, k: number) => { x: number; y: number }
  obj: { x: number; y: number; s: number }
  axisStart: { x: number; y: number }
  axisEnd: { x: number; y: number }
  /** where a name of the finale sits before compressing, and on the final line */
  finale: (i: number) => { big: { x: number; y: number }; small: { x: number; y: number } }
  textTop: number
}

export function makeLayout(w: number, h: number, mobile: boolean): Layout {
  const gut = Math.max(20, Math.min(64, w * 0.05))
  if (mobile) {
    const vx = gut + 22
    const y0 = h * 0.5
    const y1 = h * 0.9
    const frac = (i: number, k: number) => (i < 3 ? lerp(i / 3, i / 4, k) : i === 3 ? lerp(1, 0.75, k) : 1)
    return {
      w, h, mobile, gut,
      node: (i, k) => ({ x: vx, y: lerp(y0, y1, frac(i, k)) }),
      obj: { x: w * 0.7, y: h * 0.5, s: w * 0.34 },
      axisStart: { x: vx, y: y0 },
      axisEnd: { x: vx, y: y1 },
      finale: (i) => ({ big: { x: w / 2, y: h * 0.4 + i * 54 }, small: { x: vx + 24 + 0, y: lerp(y0, y1, i / 3) } }),
      textTop: NAV + 22,
    }
  }
  const x0 = gut + 48
  const x1 = w - gut - 96
  const axisY = h * 0.8
  const frac = (i: number, k: number) => (i < 3 ? lerp(i / 3, i / 4, k) : i === 3 ? lerp(1, 0.75, k) : 1)
  return {
    w, h, mobile, gut,
    node: (i, k) => ({ x: lerp(x0, x1, frac(i, k)), y: axisY }),
    obj: { x: w * 0.65, y: NAV + (h - NAV) * 0.42, s: Math.min(w * 0.24, (h - NAV) * 0.4) },
    axisStart: { x: x0, y: axisY },
    axisEnd: { x: x1, y: axisY },
    finale: (i) => ({ big: { x: w * [0.12, 0.335, 0.565, 0.83][i], y: h * 0.47 }, small: { x: lerp(x0, x1, [0, 0.34, 0.67, 1][i]), y: axisY - 26 } }),
    textTop: NAV + (h - NAV) * 0.1,
  }
}

/* ───────── Small helpers ───────── */

const sg = (t: number, a: number, b: number, e: (u: number) => number = easeInOut) => seg(t, a, b, e)
const smooth = (u: number) => u * u * (3 - 2 * u)

/** Words that rise out of a mask, one after another, and leave upwards. `into` and `out` are 0–1. */
function MaskedWords({ text, into, out = 0, stagger = 0.12, className = '' }: { text: string; into: number; out?: number; stagger?: number; className?: string }) {
  const words = text.split(' ')
  return (
    <span className={`evo-words ${className}`} aria-hidden="true">
      {words.map((word, i) => {
        const a = clamp01((into - i * stagger) / Math.max(0.01, 1 - (words.length - 1) * stagger))
        const b = clamp01((out - i * stagger * 0.5) / Math.max(0.01, 1 - (words.length - 1) * stagger * 0.5))
        const y = (1 - spring(a)) * 112 - smooth(b) * 112
        return (
          <span key={i} className="evo-mask">
            <span style={{ transform: `translateY(${y}%)`, opacity: a > 0.01 && b < 0.99 ? 1 : 0 }}>{word}</span>
          </span>
        )
      })}
    </span>
  )
}

/** One word that turns into another, letter by letter, each letter rolling through its own mask. */
function RollWord({ from, to, u, className = '' }: { from: string; to: string; u: number; className?: string }) {
  const n = Math.max(from.length, to.length)
  return (
    <span className={`evo-roll ${className}`} aria-hidden="true">
      {Array.from({ length: n }, (_, i) => {
        const p = easeInOut(clamp01((u - (i / n) * 0.45) / 0.55))
        return (
          <span key={i} className="evo-roll__cell">
            <span style={{ transform: `translateY(${-p * 100}%)` }}>{from[i] ?? ' '}</span>
            <span style={{ transform: `translateY(${(1 - p) * 100}%)` }}>{to[i] ?? ' '}</span>
          </span>
        )
      })}
    </span>
  )
}

/* ───────── The object: one body that is a thing, then a product page, then a parcel, then a point of light ───────── */

function Body({ w, h, d, rx, ry, children }: { w: number; h: number; d: number; rx: number; ry: number; children?: ReactNode }) {
  const face = (extra: CSSProperties): CSSProperties => ({ position: 'absolute', ...extra })
  return (
    <div className="evo-box" style={{ width: w, height: h, transform: `rotateX(${rx}deg) rotateY(${ry}deg)` }}>
      <div className="evo-face evo-face--front" style={face({ width: w, height: h, transform: `translateZ(${d / 2}px)` })}>
        {children}
      </div>
      <div className="evo-face evo-face--back" style={face({ width: w, height: h, transform: `rotateY(180deg) translateZ(${d / 2}px)` })} />
      <div className="evo-face evo-face--right" style={face({ width: d, height: h, left: (w - d) / 2, transform: `rotateY(90deg) translateZ(${w / 2}px)` })} />
      <div className="evo-face evo-face--left" style={face({ width: d, height: h, left: (w - d) / 2, transform: `rotateY(-90deg) translateZ(${w / 2}px)` })} />
      <div className="evo-face evo-face--top" style={face({ width: w, height: d, top: (h - d) / 2, transform: `rotateX(90deg) translateZ(${h / 2}px)` })} />
      <div className="evo-face evo-face--bottom" style={face({ width: w, height: d, top: (h - d) / 2, transform: `rotateX(-90deg) translateZ(${h / 2}px)` })} />
    </div>
  )
}

/* ───────── The stage ───────── */

interface Props {
  t: number
  layout: Layout
}

export function EvolutionStage({ t, layout: L }: Props) {
  const { w, h, mobile } = L
  const m1 = sg(t, ...T.m1)
  const m2 = sg(t, ...T.m2)
  const m3 = sg(t, ...T.m3)
  const k = m3

  /* axis + token */
  const axisIn = sg(t, 14.6, 19.5)
  const tokenU = sg(t, 19.5, 27.2, (u) => u)
  const seg3 = Math.min(2, Math.floor(tokenU * 3))
  const tokenF = tokenU >= 1 ? 1 : (seg3 + smooth(tokenU * 3 - seg3)) / 3
  const tealF = sg(t, 76.8, 85.5)
  // the old interface goes quiet while the question is asked, and comes back as the new one
  const nodeDim = t < 64 ? 1 : lerp(lerp(1, 0.16, sg(t, 64, 66.5)), 1, sg(t, 72.8, 76))

  /* finale */
  const fin = sg(t, T.finale[0] + 0.5, T.finale[0] + 4)
  const compress = sg(t, 93, 96.2)
  const finalLine = sg(t, 92.6, 96.4)
  const sceneOut = 1 - sg(t, 87.6, 90.2)

  const nodePos = (i: number) => L.node(i, k)
  const A = nodePos

  /* ---- the product body ---- */
  const base = L.obj
  const s = base.s
  const objIn = sg(t, 9.6, 14.2, spring)
  const pkgS = s * 0.4
  const toPkg = m2
  const sizeNow = lerp(s, pkgS, toPkg)
  const bodyW = sizeNow
  const bodyH = sizeNow * lerp(0.78, 0.62, toPkg)
  const dPhys = sizeNow * 0.55
  const dCard = 5
  const dNow = lerp(lerp(dPhys, dCard, m1), sizeNow * 0.62, toPkg)
  const sway = Math.sin(t * 0.7) * 3
  // isometric while it is a thing, turned flat while it is a product page, isometric again as a parcel
  const rxIso = -22
  const ryIso = -36 + Math.min(10, Math.max(0, t - 14) * 0.55)
  const ryCard = -7 + sway
  const ryParcel = -34 + Math.min(12, Math.max(0, t - 50) * 1.2)
  const rx = lerp(lerp(rxIso, 0, m1), rxIso, toPkg)
  const ry = lerp(lerp(ryIso + sway * 0.4, ryCard, m1), ryParcel, toPkg)

  // position: rests right of the copy; becomes the parcel that rides the axis
  const first = A(0)
  const lift = mobile ? 0 : 70
  const startPos = { x: first.x, y: first.y - lift }
  const travelU = sg(t, 51.5, 61, easeInOut)
  // the last leg, fulfilment to destination, is a route: a gentle arc rather than the straight spine
  const legCtrl = (() => {
    const a = A(2)
    const b = A(3)
    return mobile ? { x: Math.max(a.x, b.x) + 72, y: (a.y + b.y) / 2 } : { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - h * 0.17 }
  })()
  const along = (u: number) => {
    const f = u * 3
    const i = Math.min(2, Math.floor(f))
    const p0 = A(i)
    const p1 = A(i + 1)
    const q = smooth(f - i)
    if (i === 2) {
      const m = 1 - q
      return { x: m * m * p0.x + 2 * m * q * legCtrl.x + q * q * p1.x, y: m * m * p0.y + 2 * m * q * legCtrl.y + q * q * p1.y }
    }
    return { x: lerp(p0.x, p1.x, q), y: lerp(p0.y, p1.y, q) }
  }
  const routeIn = sg(t, 54.2, 57.4)
  const orderPop = sg(t, 53.1, 54.3, spring) * (1 - sg(t, 62.4, 64))
  const fulfilPulse = (t - 55.6) / 2.4
  const trav = along(travelU)
  const restIn = sg(t, 12.4, 16.4)
  const restPos = { x: lerp(w * 0.5, base.x, restIn), y: lerp(h * (mobile ? 0.66 : 0.7), base.y, restIn) }
  const restScale = lerp(0.6, 1, restIn)
  const toStart = { x: lerp(restPos.x, startPos.x, m2), y: lerp(restPos.y, startPos.y, m2) }
  const pos = t < 50 ? toStart : { x: trav.x, y: trav.y - lift }
  const bodyOpacity = objIn * (1 - sg(t, 66, 69.5)) * (t > 74 ? 0 : 1)
  const floatY = t < 27 ? Math.sin(t * 0.9) * 5 : 0
  const physLayer = 1 - sg(t, 28.2, 30.8)
  const uiLayer = sg(t, 29.6, 32.2) * (1 - sg(t, 46, 48.4))
  const parcelLayer = sg(t, 47.2, 49.6)
  const searchBar = sg(t, 37.6, 40.4)
  const ghost = sg(t, 41.0, 42.8) * (1 - sg(t, 45.4, 46.6))
  const buyPress = sg(t, 45.2, 45.5) * (1 - sg(t, 45.5, 46))
  const added = sg(t, 45.6, 46.6)

  /* ---- cursor ---- */
  const cursor = (() => {
    const stops: [number, { x: number; y: number }][] = [
      [32.2, { x: w * 0.92, y: h * 0.96 }],
      [34.3, { x: A(0).x + 10, y: A(0).y + 12 }],
      [37.3, { x: A(1).x + 10, y: A(1).y + 12 }],
      [40.5, { x: A(2).x + 10, y: A(2).y + 12 }],
      [43.3, { x: A(3).x + 10, y: A(3).y + 12 }],
      [45.1, { x: base.x + s * 0.22, y: base.y + s * 0.3 }],
      [47.5, { x: base.x + s * 0.22, y: base.y + s * 0.3 }],
      [50.6, { x: A(0).x + 10, y: A(0).y + 12 }],
      [59.5, { x: A(2).x + 10, y: A(2).y + 12 }],
    ]
    if (t < stops[0][0]) return { ...stops[0][1], o: 0 }
    let i = 0
    while (i < stops.length - 2 && t >= stops[i + 1][0]) i++
    const [ta, pa] = stops[i]
    const [tb, pb] = stops[i + 1]
    const u = t >= tb ? 1 : smooth(clamp01((t - ta) / (tb - ta)))
    const arc = Math.sin(Math.PI * u) * 22
    const o = sg(t, 32.2, 33.4) * (1 - sg(t, 65.5, 68.5)) * (t > 62 ? 0.55 + 0.45 * (1 - sg(t, 62, 64)) : 1)
    return { x: lerp(pa.x, pb.x, u) - arc * 0.4, y: lerp(pa.y, pb.y, u) - arc, o }
  })()
  const clicks = [34.6, 37.6, 41.0, 43.6, 45.4, 51.0]
  const press = clicks.reduce((m, c) => Math.min(m, 1 - 0.18 * Math.max(0, 1 - Math.abs(t - c) / 0.16)), 1)

  /* ---- title / statement per stage ---- */
  const titleBlock = (i: number) => {
    const st = STAGES[i]
    const [a, b] = st.window
    const into = sg(t, a + 0.3, a + 2.6, (u) => u)
    const out = sg(t, b - 1.8, b, (u) => u)
    return { into, out, vis: into > 0.001 && out < 0.999, st }
  }

  return (
    <div className="evo-stage" style={{ width: w, height: h }}>
      {/* hand-over: the ground turns from ivory to the next section's white, behind everything else */}
      <div className="evo-release" style={{ opacity: sg(t, 97.5, 100) }} />
      {/* opening statements */}
      {OPENING.map((line, i) => {
        const [a, b] = i === 0 ? T.open1 : T.open2
        const into = sg(t, a, a + 2.4, (u) => u)
        const out = sg(t, b - 1.4, b, (u) => u)
        if (into <= 0.001 || out >= 0.999) return null
        return (
          <p key={line} className={`evo-open ${i === 1 ? 'is-second' : ''}`} style={{ top: h * (mobile ? 0.3 : 0.32) }}>
            <MaskedWords text={line} into={into} out={out} stagger={0.1} />
          </p>
        )
      })}

      {/* the spine */}
      <svg className="evo-svg" width={w} height={h} aria-hidden="true">
        {axisIn > 0 ? (
          <>
            <line x1={L.axisStart.x} y1={L.axisStart.y} x2={lerp(L.axisStart.x, L.axisEnd.x, axisIn)} y2={lerp(L.axisStart.y, L.axisEnd.y, axisIn)} className="evo-axis" opacity={sceneOut * (t < 64 ? 1 : lerp(1, 0.25, sg(t, 64, 66)))} />
            {t < 28 && tokenU > 0 ? (
              <line x1={L.axisStart.x} y1={L.axisStart.y} x2={lerp(L.axisStart.x, L.axisEnd.x, tokenF)} y2={lerp(L.axisStart.y, L.axisEnd.y, tokenF)} className="evo-axis evo-axis--ink" opacity={1 - sg(t, 27, 29.5)} />
            ) : null}
            {tealF > 0 ? <line x1={L.axisStart.x} y1={L.axisStart.y} x2={lerp(L.axisStart.x, L.axisEnd.x, tealF)} y2={lerp(L.axisStart.y, L.axisEnd.y, tealF)} className="evo-axis evo-axis--teal" opacity={sceneOut} /> : null}
          </>
        ) : null}
        {/* quick lines behind the parcel: speed */}
        {t > 51.5 && t < 61.5
          ? [0, 1, 2].map((n) => {
              const lag = 0.05 + n * 0.035
              const p = along(clamp01(travelU - lag))
              const sp = Math.sin(Math.PI * travelU)
              return <line key={n} x1={p.x} y1={p.y - lift + (n - 1) * 9} x2={trav.x} y2={trav.y - lift + (n - 1) * 9} className="evo-speed" opacity={sp * 0.55} />
            })
          : null}
        {/* fast commerce: the route, the confirmation, the point of fulfilment */}
        {t > 53 && t < 66 ? (
          <g opacity={1 - sg(t, 63, 65)}>
            {routeIn > 0 ? <path d={`M${A(2).x} ${A(2).y} Q${legCtrl.x} ${legCtrl.y} ${A(3).x} ${A(3).y}`} className="evo-route" pathLength={1} strokeDasharray="0.012 0.02" strokeDashoffset={1 - routeIn} /> : null}
            {orderPop > 0.01 ? (
              <g transform={`translate(${A(1).x} ${A(1).y - (mobile ? 46 : 62)})`}>
                <circle r={17 * orderPop} className="evo-badge" />
                <path d="M-6.5 0.5 L-2 5 L7 -5" className="evo-badge__tick" pathLength={1} strokeDasharray="1" strokeDashoffset={1 - sg(orderPop, 0.45, 1)} />
              </g>
            ) : null}
            {fulfilPulse > 0 && fulfilPulse < 1
              ? [0, 0.33].map((o) => {
                  const u = clamp01(fulfilPulse - o) / (1 - o)
                  return u > 0 ? <circle key={o} cx={A(2).x} cy={A(2).y} r={30 + 46 * u} className="evo-pulse" opacity={(1 - u) * 0.7} /> : null
                })
              : null}
          </g>
        ) : null}
        {/* intelligence: as the line reaches each step, that step answers with one quiet ring. No hand on the mouse. */}
        {tealF > 0 && sceneOut > 0.01
          ? [0, 1, 2, 3, 4].map((i) => {
              const u = clamp01((tealF - (i === 4 ? 1 : i / 4) + 0.02) / 0.16)
              if (u <= 0 || u >= 1) return null
              const p = A(i)
              return <circle key={i} cx={p.x} cy={p.y} r={(mobile ? 24 : 32) + (mobile ? 22 : 34) * u} className="evo-pulse evo-pulse--teal" opacity={(1 - u) * 0.8 * sceneOut} />
            })
          : null}
        {/* the finale line */}
        {finalLine > 0 ? (
          <g>
            <line x1={L.axisStart.x} y1={L.axisStart.y} x2={lerp(L.axisStart.x, L.axisEnd.x, finalLine)} y2={lerp(L.axisStart.y, L.axisEnd.y, finalLine)} className="evo-axis evo-axis--teal evo-axis--final" opacity={sg(t, 92.6, 94)} />
            {FINALE_NAMES.map((_, i) => {
              const p = L.finale(i).small
              const dx = mobile ? L.axisStart.x : p.x
              const dy = mobile ? p.y : L.axisStart.y
              const on = sg(finalLine, i / 4 + 0.02, i / 4 + 0.22)
              return on > 0 ? <circle key={i} cx={dx} cy={dy} r={(i === 3 ? 7 : 5) * on} className={i === 3 ? 'evo-fdot evo-fdot--teal' : 'evo-fdot'} /> : null
            })}
          </g>
        ) : null}
      </svg>

      {/* the product body */}
      {bodyOpacity > 0.005 ? (
        <div className="evo-persp" style={{ left: pos.x, top: pos.y + floatY, opacity: bodyOpacity * (t < 64 ? 1 : 1 - sg(t, 64, 66) * 0.7), transform: `translate(-50%, -50%) translateY(${(1 - objIn) * 46}px) scale(${lerp(0.82, 1, objIn) * restScale})` }}>
          <Body w={bodyW} h={bodyH} d={dNow} rx={rx} ry={ry}>
            <div className="evo-layer" style={{ opacity: physLayer }}>
              <Cog className="evo-cog" strokeWidth={0.9} style={{ width: bodyW * 0.5, height: bodyW * 0.5 }} />
              <i className="evo-strap" />
            </div>
            <div className="evo-layer evo-ui" style={{ opacity: uiLayer }}>
              <span className="evo-ui__search" style={{ width: `${20 + 70 * searchBar}%`, opacity: searchBar }} />
              <span className="evo-ui__img"><Cog strokeWidth={0.9} /></span>
              <span className="evo-ui__line" />
              <span className="evo-ui__line is-short" />
              <span className="evo-ui__price" />
              <span className="evo-ui__buy" style={{ transform: `scale(${1 - 0.07 * buyPress})`, background: added > 0.5 ? 'var(--ink)' : undefined }}>
                {added > 0.5 ? <Check strokeWidth={3} /> : null}
              </span>
            </div>
            <div className="evo-layer evo-parcel" style={{ opacity: parcelLayer }}>
              <i className="evo-tape" />
              <i className="evo-tape is-cross" />
            </div>
          </Body>
          {ghost > 0.01 ? (
            <div className="evo-ghost" style={{ width: bodyW, height: bodyH, opacity: ghost * 0.9, transform: `translate(${bodyW * (0.12 + 0.5 * ghost)}px, ${-bodyH * 0.06}px) rotateY(${ryCard}deg)` }}>
              <span className="evo-ui__img" />
              <span className="evo-ui__line" />
              <span className="evo-ui__line is-short" />
            </div>
          ) : null}
          {t > 56.5 && t < 66 ? <Arrival at={sg(t, 59.4, 61.4)} size={bodyW} /> : null}
        </div>
      ) : null}

      {/* nodes */}
      {Array.from({ length: 5 }, (_, i) => {
        const p = nodePos(i)
        const appear = i < 4 ? sg(t, 15.2 + i * 0.55, 17.2 + i * 0.55, spring) : k
        if (appear <= 0.003) return null
        // what this node shows, and how far it is into the next stage (each node a beat behind its neighbour)
        const raw = (m: number) => easeInOut(clamp01((m - i * 0.1) / 0.7))
        let from = NODES[0][Math.min(i, 3)]
        let to = from
        let u = 0
        if (i === 4) {
          from = to = NODES[3][4]
        } else if (t < T.m1[1]) {
          from = NODES[0][i]
          to = NODES[1][i]
          u = raw(m1)
        } else if (t < T.m2[1]) {
          from = NODES[1][i]
          to = NODES[2][i]
          u = raw(m2)
        } else {
          from = NODES[2][i]
          to = NODES[3][i]
          u = raw(m3)
        }
        const lit = t < 28 ? (tokenF + 0.001 >= i / 3 ? 1 : 0) : 1
        const tealOn = t > 76 ? (tealF + 0.02 >= (i === 4 ? 1 : i / 4) ? 1 : 0) : 0
        const Fi = from.icon
        const Ti = to.icon
        const labelOut = (u: number) => `translateY(${-u * 110}%)`
        const labelIn = (u: number) => `translateY(${(1 - u) * 110}%)`
        const nodeOpacity = appear * nodeDim * sceneOut
        const size = mobile ? 44 : 58
        const hitNode = [0, 1, 2, 3, -1, 0]
        const clicked = clicks.some((c, n) => hitNode[n] === i && Math.abs(t - c - 0.08) < 0.35)
        return (
          <div key={i} className={`evo-node ${tealOn ? 'is-teal' : ''} ${lit ? 'is-lit' : ''} ${clicked ? 'is-hit' : ''}`} style={{ left: p.x, top: p.y, opacity: nodeOpacity, transform: `translate(-50%, -50%) scale(${lerp(0.6, 1, appear) * (clicked ? 1.1 : 1)})` }}>
            <span className="evo-node__disc" style={{ width: size, height: size }}>
              <Fi size={size * 0.44} strokeWidth={1.5} style={{ opacity: 1 - u, transform: `scale(${1 - u * 0.4}) rotate(${u * -30}deg)` }} />
              <Ti size={size * 0.44} strokeWidth={1.5} style={{ opacity: u, transform: `scale(${0.6 + u * 0.4}) rotate(${(1 - u) * 30}deg)`, position: 'absolute' }} />
            </span>
            <span className={`evo-node__label ${mobile ? 'is-side' : ''}`}>
              <span className="evo-mask">
                <span style={{ transform: u < 1 ? labelOut(u) : 'translateY(-110%)', position: 'relative' }}>{from.label}</span>
              </span>
              <span className="evo-mask evo-mask--over">
                <span style={{ transform: labelIn(u) }}>{to.label}</span>
              </span>
            </span>
          </div>
        )
      })}

      {/* stage titles */}
      {STAGES.map((st, i) => {
        const tb = titleBlock(i)
        if (!tb.vis) return null
        return (
          <div key={st.id} className={`evo-copy ${st.id === 'agentic-commerce' ? 'is-agentic' : ''}`} style={{ top: L.textTop, left: L.gut, opacity: sceneOut }}>
            <h2 className="evo-title" aria-hidden="true">
              <MaskedWords text={st.title} into={tb.into} out={tb.out} stagger={0.2} />
            </h2>
            <p className="evo-statement" aria-hidden="true" style={{ opacity: sg(tb.into, 0.35, 1) * (1 - tb.out), transform: `translateY(${(1 - sg(tb.into, 0.35, 1)) * 14}px)` }}>
              {st.statement}
            </p>
          </div>
        )
      })}

      {/* the three lines of the agentic stage */}
      {AGENTIC_LINES.map((ln) => {
        const into = sg(t, ln.at[0], ln.at[0] + 1.6, (u) => u)
        const out = sg(t, ln.at[1] - 1, ln.at[1], (u) => u)
        if (into <= 0.001 || out >= 0.999) return null
        return (
          <p key={ln.text} className="evo-line" style={{ left: L.gut, top: mobile ? h * 0.34 : h * 0.5, opacity: sceneOut }}>
            <MaskedWords text={ln.text} into={into} out={out} stagger={0.07} />
          </p>
        )
      })}

      {/* the question, and the words that change */}
      {t > T.question[0] - 0.5 && t < 77 ? (
        <>
          <p className="evo-question" style={{ top: h * (mobile ? 0.2 : 0.24) }}>
            <MaskedWords text={QUESTION} into={sg(t, T.question[0], T.question[0] + 2.8, (u) => u)} out={sg(t, 74, 75.8, (u) => u)} stagger={0.06} />
          </p>
          <div className="evo-morphs" style={{ top: h * (mobile ? 0.4 : 0.44), opacity: 1 - sg(t, 75.2, 77) }}>
            {MORPHS.map(([a, b], i) => {
              const into = sg(t, 66.8 + i * 0.4, 68.2 + i * 0.4)
              const u = sg(t, 69.2 + i * 1.0, 71.0 + i * 1.0)
              if (into <= 0.001) return null
              return (
                <div key={a} className="evo-morph" style={{ opacity: into, transform: `translateY(${(1 - into) * 16}px)` }}>
                  <RollWord from={a} to={b} u={u} className={u > 0.5 ? 'is-to' : ''} />
                </div>
              )
            })}
          </div>
        </>
      ) : null}

      {/* the four stages as one line */}
      {fin > 0.001
        ? FINALE_NAMES.map((name, i) => {
            const f = L.finale(i)
            const inn = sg(t, 89 + i * 0.7, 91.4 + i * 0.7)
            const px = lerp(f.big.x, mobile ? f.small.x + 54 : f.small.x, compress)
            const py = lerp(f.big.y, f.small.y, compress)
            const fs = lerp(mobile ? 22 : Math.max(20, Math.min(40, w * 0.026)), mobile ? 13 : 14, compress)
            return (
              <div key={name} className={`evo-fname ${i === 3 ? 'is-agentic' : ''}`} style={{ left: px, top: py, fontSize: fs, opacity: inn, transform: `translate(${mobile && compress > 0.5 ? '0' : '-50%'}, -50%)` }}>
                <MaskedWords text={name} into={inn} stagger={0.18} />
              </div>
            )
          })
        : null}
      {fin > 0.001 && compress < 0.6
        ? [0, 1, 2].map((i) => {
            const a = L.finale(i).big
            const b = L.finale(i + 1).big
            const mx = (a.x + b.x) / 2
            const my = (a.y + b.y) / 2
            const o = sg(t, 90.5 + i * 0.7, 91.6 + i * 0.7) * (1 - sg(t, 92.4, 93.4))
            return (
              <span key={i} className="evo-arrow" style={{ left: mobile ? a.x : mx, top: mobile ? (a.y + b.y) / 2 : my, opacity: o, transform: `translate(-50%, -50%) ${mobile ? 'rotate(90deg)' : ''}` }}>
                →
              </span>
            )
          })
        : null}
      <p className="evo-final" style={{ top: h * (mobile ? 0.22 : 0.27) }}>
        <MaskedWords text={FINALE_LINE} into={sg(t, 94.4, 97.4, (u) => u)} stagger={0.1} />
      </p>
      <div className="evo-logo" style={{ opacity: sg(t, 96.6, 99.2), transform: `translate(-50%, ${(1 - sg(t, 96.6, 99.2)) * 12}px)`, top: mobile ? h * 0.36 : L.axisStart.y + 64 }}>
        <img src={logo} alt="" height={44} />
      </div>

      {/* cursor */}
      {cursor.o > 0.01 ? (
        <div className="evo-cursor" style={{ transform: `translate(${cursor.x}px, ${cursor.y}px) scale(${press})`, opacity: cursor.o }}>
          <svg width="26" height="32" viewBox="0 0 30 36" aria-hidden="true">
            <path d="M2 2 L2 28 L9.2 21.4 L14.2 33 L19.6 30.6 L14.6 19.2 L24.4 19.2 Z" fill="#14181a" stroke="#fff" strokeWidth="2.2" strokeLinejoin="round" />
          </svg>
        </div>
      ) : null}

    </div>
  )
}

function Arrival({ at, size }: { at: number; size: number }) {
  if (at <= 0.01) return null
  return (
    <span className="evo-arrival" style={{ width: size * 1.7, height: size * 1.7, opacity: at }}>
      <i style={{ transform: `scale(${0.4 + at * 0.6})` }} />
      <i style={{ transform: `scale(${0.7 + at * 0.6})`, opacity: 0.5 }} />
    </span>
  )
}

