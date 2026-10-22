import React from 'react'
import { Img, staticFile } from 'remotion'
import { Abs, C, FONT, TriField, lerp, p, pop } from '../lib'

const CHECKS = ['OEM match · fits NV-4500', 'Cross-referenced  AS-411-C → NVM-1040-HY', 'In stock · 6 depots']

export const CARD = { x: 90, y: 760, w: 900, h: 420 }
/** Where the answer card starts in the next scene: over the shrunken phone at the end of this one. */
export const CARD_END = { x: 540 - 450 * 0.55, y: 440, s: 0.55 }

/** The answer card. `checks` = 0..3 rows revealed (fractional animates). */
export const AnswerCard: React.FC<{ checks: number; style?: React.CSSProperties }> = ({ checks, style }) => (
  <div style={{
    width: CARD.w, height: CARD.h, borderRadius: 34, background: C.white, boxShadow: '0 30px 80px rgba(16,32,96,0.18)',
    border: '2px solid #E3E9FA', padding: 30, boxSizing: 'border-box', fontFamily: FONT, color: C.ink, ...style,
  }}>
    <div style={{ display: 'flex', gap: 28 }}>
      <div style={{ width: 230, height: 170, borderRadius: 22, overflow: 'hidden', background: '#F2F4F8', flexShrink: 0 }}>
        <Img src={staticFile('tiltcyl.jpg')} style={{ width: '100%', height: '100%', objectFit: 'cover', transform: 'scale(1.15)' }} />
      </div>
      <div style={{ paddingTop: 8 }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: C.blue, letterSpacing: 2 }}>OEM REPLACEMENT</div>
        <div style={{ fontSize: 54, fontWeight: 800, letterSpacing: -1, marginTop: 6 }}>NVM-1040-HY</div>
        <div style={{ fontSize: 28, color: C.muted, marginTop: 4 }}>Tilt cylinder, double-acting</div>
      </div>
    </div>
    <div style={{ marginTop: 26, display: 'flex', flexDirection: 'column', gap: 14 }}>
      {CHECKS.map((c, i) => {
        const k = Math.max(0, Math.min(1, checks - i))
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 16, opacity: k, transform: `translateX(${(1 - k) * 30}px)` }}>
            <svg width={36} height={36}>
              <circle cx={18} cy={18} r={18} fill={C.green} />
              <path d="M 10 18 L 16 24 L 27 12" stroke="white" strokeWidth={4} fill="none" strokeLinecap="round" strokeLinejoin="round"
                strokeDasharray={30} strokeDashoffset={30 * (1 - k)} />
            </svg>
            <div style={{ fontSize: 30, fontWeight: 600 }}>{c}</div>
          </div>
        )
      })}
    </div>
  </div>
)

// Real screen recording of Parts Intelligence (scripts/record_platform.py), 30 fps.
const REC_FRAMES = 337
// scene time -> recording time: typing, thinking, answer + scroll, (cut the loading) part page
const SEGS: [number, number, number, number][] = [
  [0.0, 0.25, 0.5, 0.5],
  [0.25, 1.45, 0.7, 2.5],
  [1.45, 2.05, 2.5, 3.87],
  [2.05, 4.15, 3.87, 7.0],
  [4.15, 6.0, 8.47, 11.6],
]
const recTime = (t: number) => {
  for (const [a, b, ra, rb] of SEGS) if (t <= b) return ra + (rb - ra) * Math.max(0, (t - a) / (b - a))
  return 11.6
}

const PHONE = { w: 640, h: 1138, bezel: 14 }

const Callout: React.FC<{ t: number; at: number; side: 'l' | 'r'; y: number; children: React.ReactNode }> = ({ t, at, side, y, children }) => {
  const k = pop(t, at, 0.45)
  if (k <= 0) return null
  return (
    <div style={{
      position: 'absolute', top: y, [side === 'l' ? 'left' : 'right']: 36, transform: `scale(${k})`, transformOrigin: side === 'l' ? '0% 50%' : '100% 50%',
      display: 'flex', alignItems: 'center', gap: 14, padding: '16px 24px', borderRadius: 22, background: C.white,
      boxShadow: '0 18px 50px rgba(16,32,96,0.22)', border: '2px solid #E3E9FA', fontFamily: FONT, fontSize: 28, fontWeight: 700, color: C.ink,
    }}>
      <svg width={34} height={34} style={{ flexShrink: 0 }}>
        <circle cx={17} cy={17} r={17} fill={C.green} />
        <path d="M 9 17 L 15 23 L 25 11" stroke="white" strokeWidth={4} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {children}
    </div>
  )
}

/** 8–14s: ask your own AI. Real footage of the Noordveld Parts Intelligence app inside a phone. */
export const Yoa: React.FC<{ t: number }> = ({ t }) => {
  const enter = p(t, 0, 0.55)
  const lift = p(t, 3.95, 4.6)
  const frame = Math.min(REC_FRAMES, Math.max(1, Math.round(recTime(t) * 30) + 1))
  const scale = lerp(0.94, 1, enter) * lerp(1, 0.78, lift)

  return (
    <Abs style={{ background: C.bg, fontFamily: FONT, overflow: 'hidden' }}>
      <Abs style={{ background: `radial-gradient(50% 30% at ${20 + t * 4}% 20%, rgba(43,75,255,0.14), transparent 70%), radial-gradient(45% 30% at ${85 - t * 3}% 80%, rgba(34,184,232,0.16), transparent 70%)` }} />
      <TriField t={t} seed={11} count={50} opacity={0.35} size={[8, 18]} />

      {/* phone with the live recording */}
      <div style={{
        position: 'absolute', left: 540 - PHONE.w / 2, top: 140, width: PHONE.w, height: PHONE.h,
        transform: `translateY(${(1 - enter) * 160 - lift * 30}px) scale(${scale}) rotate(${(1 - enter) * 3}deg)`, transformOrigin: '50% 0%',
        opacity: enter, borderRadius: 78, background: '#0B1533', padding: PHONE.bezel, boxSizing: 'border-box',
        boxShadow: '0 50px 120px rgba(16,32,96,0.30), inset 0 0 0 2px #2A3B7A',
      }}>
        <div style={{ position: 'relative', width: '100%', height: '100%', borderRadius: 64, overflow: 'hidden', background: '#F5F5F0' }}>
          <Img src={staticFile(`platform/${String(frame).padStart(4, '0')}.jpg`)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <div style={{ position: 'absolute', top: 14, left: '50%', width: 150, height: 34, marginLeft: -75, borderRadius: 20, background: '#0B1533' }} />
        </div>
      </div>

      {/* what the platform just did, called out */}
      <Callout t={t} at={2.25} side="l" y={lerp(780, 600, lift)}>AS-411-C = NVM-1040-HY</Callout>
      <Callout t={t} at={2.8} side="r" y={lerp(930, 740, lift)}>Verified in your catalogue</Callout>
      <Callout t={t} at={4.55} side="l" y={420}>Fits your NV-4500</Callout>
      <Callout t={t} at={4.95} side="r" y={300}>In stock · 6 depots</Callout>

      {/* YOA title */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 1060, textAlign: 'center' }}>
        <div style={{ position: 'absolute', left: '50%', top: 90, width: 900, height: 420, transform: `translate(-50%,-50%) scale(${p(t, 4.1, 5.0)})`, background: 'radial-gradient(closest-side, rgba(43,75,255,0.16), transparent)' }} />
        <div style={{ overflow: 'hidden' }}>
          <div style={{
            fontSize: 150, fontWeight: 800, letterSpacing: -4, lineHeight: 1,
            background: `linear-gradient(90deg, ${C.blue}, ${C.sky} 55%, ${C.cyan})`, WebkitBackgroundClip: 'text', color: 'transparent',
            transform: `translateY(${(1 - p(t, 4.2, 4.9)) * 110}%)`,
          }}>YOA</div>
        </div>
        <div style={{ fontSize: 50, fontWeight: 700, color: C.ink, marginTop: 14, opacity: p(t, 4.5, 5.0), transform: `translateY(${(1 - p(t, 4.5, 5.1)) * 30}px)` }}>
          Build your own AI.
        </div>
        <div style={{ fontSize: 36, fontWeight: 500, color: C.muted, marginTop: 10, opacity: p(t, 4.8, 5.3), transform: `translateY(${(1 - p(t, 4.8, 5.4)) * 30}px)` }}>
          Run by your IT team, or by us.
        </div>
      </div>
    </Abs>
  )
}
