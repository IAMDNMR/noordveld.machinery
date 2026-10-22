import React from 'react'
import { Abs, C, FONT, TRI, Words, inE, inOutE, lerp, p, rng, triPoints } from '../lib'
import { AnswerCard, CARD, CARD_END } from './Yoa'

const CELL = 36
const COLS = CARD.w / CELL
const ROWS = Math.ceil(CARD.h / CELL)

type Shard = { x: number; y: number; flip: boolean; vx: number; vy: number; rot: number; tx: number; ty: number; c: string; d: number }

// Shards of the answer card, each with an explosion vector and a resting place in the data bed below.
const SHARDS: Shard[] = (() => {
  const r = rng(42)
  const out: Shard[] = []
  for (let row = 0; row < ROWS; row++) {
    for (let col = 0; col < COLS; col++) {
      for (const flip of [false, true]) {
        const x = CARD.x + col * CELL + (flip ? CELL * 0.66 : CELL * 0.33)
        const y = CARD.y + row * CELL + (flip ? CELL * 0.66 : CELL * 0.33)
        const ang = Math.atan2(y - (CARD.y + CARD.h / 2), x - 540) + (r() - 0.5) * 0.9
        const sp = 140 + r() * 420
        const layer = Math.floor(r() * 6) // 0 = deepest
        const tx = 40 + r() * 1000
        const ty = 1690 - layer * 52 - r() * 40
        out.push({ x, y, flip, vx: Math.cos(ang) * sp * 1.2, vy: Math.sin(ang) * sp * 0.45 + 90, rot: (r() - 0.5) * 540, tx, ty, c: TRI[5 - layer], d: r() * 0.25 })
      }
    }
  }
  return out
})()

/** 14.5–17.5s: the answer card breaks into the logo's triangles; they settle as the data beneath. */
export const Turn: React.FC<{ t: number }> = ({ t }) => {
  const cover = p(t, 0, 0.3)
  const move = p(t, 0.05, 0.6, inOutE)
  const cx = lerp(CARD_END.x, CARD.x, move)
  const cy = lerp(CARD_END.y, CARD.y, move)
  const cs = lerp(CARD_END.s, 1, move)
  const broken = t >= 0.72
  const out = p(t, 2.6, 3.0, inE)

  return (
    <Abs style={{ fontFamily: FONT }}>
      <Abs style={{ background: C.bg, opacity: cover }} />

      {!broken && (
        <div style={{ position: 'absolute', left: cx, top: cy, transform: `scale(${cs})`, transformOrigin: '0 0' }}>
          <AnswerCard checks={3} />
          {/* crack flash just before it breaks */}
          <Abs style={{ borderRadius: 34, background: 'white', opacity: p(t, 0.55, 0.72, (x) => x) * 0.9 }} />
        </div>
      )}

      {broken && (
        <svg width={1080} height={1920} style={{ position: 'absolute', inset: 0 }}>
          {SHARDS.map((s, i) => {
            const e = p(t, 0.72, 1.35 + s.d * 0.4) // explode
            const g = p(t, 1.25 + s.d, 2.35 + s.d, inOutE) // settle
            const ex = s.x + s.vx * e
            const ey = s.y + s.vy * e + 160 * e * e
            const x = lerp(ex, s.tx, g)
            const y = lerp(ey, s.ty, g)
            const rot = lerp((s.flip ? 180 : 0) + s.rot * e, 0, g)
            const size = lerp(CELL * 0.95, 20, Math.max(e * 0.4, g))
            const white = 1 - p(t, 0.72, 0.95, (k) => k)
            return (
              <polygon key={i} points={triPoints(size)} transform={`translate(${x} ${y}) rotate(${rot})`}
                fill={white > 0.02 ? '#FFFFFF' : s.c} opacity={white > 0.02 ? 1 : 0.92} stroke={white > 0.02 ? s.c : 'none'} strokeWidth={white * 2} />
            )
          })}
        </svg>
      )}

      {/* headline */}
      <div style={{ position: 'absolute', left: 40, right: 40, top: 330, opacity: 1 - out }}>
        <Words t={t} at={0.45} step={0.08} text="AI is only as smart as"
          style={{ fontSize: 84, fontWeight: 800, color: C.ink, letterSpacing: -2, lineHeight: 1.05 }} />
        <Words t={t} at={0.95} step={0.09} text="the data beneath it."
          style={{ fontSize: 84, fontWeight: 800, letterSpacing: -2, lineHeight: 1.05, marginTop: 6 }}
          accent={() => ({ background: `linear-gradient(90deg, ${C.blue}, ${C.cyan})`, WebkitBackgroundClip: 'text', color: 'transparent' })} />
      </div>
      {/* arrow pointing down into the data */}
      <svg width={80} height={300} style={{ position: 'absolute', left: 500, top: 1000, opacity: p(t, 1.9, 2.3) * (1 - out) }}>
        <line x1={40} y1={0} x2={40} y2={250 * p(t, 1.9, 2.5)} stroke={C.sky} strokeWidth={6} strokeDasharray="14 12" strokeDashoffset={-t * 60} />
        <polygon points="18,250 62,250 40,290" fill={C.sky} opacity={p(t, 2.3, 2.5)} />
      </svg>

      <Abs style={{ background: C.bg, opacity: out }} />
    </Abs>
  )
}
