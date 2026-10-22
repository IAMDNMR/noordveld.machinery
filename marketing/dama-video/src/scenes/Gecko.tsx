import React from 'react'
import { Img, staticFile } from 'remotion'
import { Abs, C, FONT, TRI, TriField, inE, inOutE, lerp, p, pop, rng, triPoints } from '../lib'

const SOURCES = [
  { label: 'ERP', x: 170, y: 330, c: C.blue },
  { label: 'CRM', x: 410, y: 250, c: C.sky },
  { label: 'Legacy', x: 670, y: 250, c: '#1E3A8A' },
  { label: 'DWH', x: 910, y: 330, c: C.cyan },
]
const MERGE = { x: 540, y: 700 }
const INTO = { x: 540, y: 930 }

type Pt = { x: number; y: number }
const bez = (a: Pt, b: Pt, c: Pt, d: Pt, u: number): Pt => {
  const v = 1 - u
  return {
    x: v * v * v * a.x + 3 * v * v * u * b.x + 3 * v * u * u * c.x + u * u * u * d.x,
    y: v * v * v * a.y + 3 * v * v * u * b.y + 3 * v * u * u * c.y + u * u * u * d.y,
  }
}
const pathFor = (s: Pt) => {
  const a = { x: s.x, y: s.y + 50 }
  const b = { x: s.x, y: s.y + 250 }
  const c = { x: MERGE.x, y: MERGE.y - 220 }
  return { a, b, c, d: MERGE }
}

const AGENTS = [
  { logo: 'falcon.png', shot: 'shot-falcon.png', pos: '0% 0%', verb: 'maps', line: 'Source to target, field by field', at: 3.3 },
  { logo: 'cheetah.png', shot: 'shot-cheetah.png', pos: '10% 30%', verb: 'builds', line: 'Production-ready transformation code', at: 3.6 },
  { logo: 'owl.png', shot: 'shot-owl.png', pos: '0% 0%', verb: 'checks', line: 'Data quality before production', at: 3.9 },
]

/** 17–27s: sources flow into one stream → BlueGecko → Falcon maps · Cheetah builds · Owl checks → 70%. */
export const Gecko: React.FC<{ t: number }> = ({ t }) => {
  const flowOut = p(t, 3.0, 3.4, inE)
  const wipe = p(t, 5.75, 6.25, inOutE)
  const pct = Math.round(70 * p(t, 7.1, 8.1, (x) => 1 - Math.pow(1 - x, 3)))
  const r = rng(5)
  const particles = Array.from({ length: 64 }, (_, i) => ({ src: i % 4, off: r(), sp: 0.55 + r() * 0.35, s: 14 + r() * 12, c: TRI[2 + Math.floor(r() * 4)] }))

  return (
    <Abs style={{ background: C.white, fontFamily: FONT, overflow: 'hidden' }}>
      <Abs style={{ background: `radial-gradient(60% 35% at 50% 70%, rgba(34,184,232,0.14), transparent 70%)` }} />
      <TriField t={t} seed={21} count={36} opacity={0.22} size={[8, 16]} />

      {/* ---- part 1: sources → one stream → BlueGecko ---- */}
      <div style={{ position: 'absolute', inset: 0, opacity: 1 - flowOut, transform: `translateY(${-flowOut * 80}px)` }}>
        <svg width={1080} height={1920} style={{ position: 'absolute' }}>
          {SOURCES.map((s, i) => {
            const { a, b, c, d } = pathFor(s)
            const draw = p(t, 0.6 + i * 0.12, 1.3 + i * 0.12)
            return (
              <path key={i} d={`M ${a.x} ${a.y} C ${b.x} ${b.y} ${c.x} ${c.y} ${d.x} ${d.y}`} stroke={s.c} strokeWidth={6}
                fill="none" strokeLinecap="round" opacity={0.28} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - draw} />
            )
          })}
          <line x1={MERGE.x} y1={MERGE.y} x2={INTO.x} y2={MERGE.y + (INTO.y - MERGE.y) * p(t, 1.1, 1.5)} stroke={C.blue} strokeWidth={16} strokeLinecap="round" opacity={0.25} />
          {/* particles riding the streams */}
          {t > 0.9 && particles.map((q, i) => {
            const life = ((t - 0.9) * q.sp + q.off) % 1
            const s = SOURCES[q.src]
            const { a, b, c, d } = pathFor(s)
            let pt: Pt
            let ang: number
            if (life < 0.72) {
              const u = life / 0.72
              pt = bez(a, b, c, d, u)
              const n = bez(a, b, c, d, Math.min(1, u + 0.02))
              ang = (Math.atan2(n.y - pt.y, n.x - pt.x) * 180) / Math.PI
            } else {
              const u = (life - 0.72) / 0.28
              pt = { x: MERGE.x + Math.sin(i) * 8, y: lerp(MERGE.y, INTO.y, u) }
              ang = 90
            }
            const born = p(t, 0.9 + q.off * 0.6, 1.2 + q.off * 0.6)
            return <polygon key={i} points={triPoints(q.s)} fill={q.c} opacity={born} transform={`translate(${pt.x} ${pt.y}) rotate(${ang})`} />
          })}
        </svg>
        {SOURCES.map((s, i) => {
          const k = pop(t, 0.45 + i * 0.12, 0.5)
          return (
            <div key={i} style={{
              position: 'absolute', left: s.x, top: s.y, transform: `translate(-50%,-50%) scale(${k})`, display: 'flex', alignItems: 'center', gap: 14,
              padding: '18px 30px', background: C.white, borderRadius: 999, boxShadow: '0 14px 40px rgba(16,32,96,0.14)', border: `3px solid ${s.c}`,
              fontSize: 38, fontWeight: 800, color: C.ink,
            }}>
              <span style={{ width: 22, height: 22, borderRadius: 6, background: s.c }} />{s.label}
            </div>
          )
        })}
        {/* BlueGecko */}
        <div style={{ position: 'absolute', left: 540, top: 1260, transform: `translate(-50%,-50%) scale(${pop(t, 0.2, 0.6)})` }}>
          <div style={{ position: 'absolute', inset: -60, borderRadius: '50%', background: 'radial-gradient(closest-side, rgba(34,184,232,0.25), transparent)', transform: `scale(${1 + 0.06 * Math.sin(t * 5)})` }} />
          <Img src={staticFile('bluegecko.png')} style={{ width: 640, position: 'relative' }} />
        </div>
      </div>

      {/* ---- part 2: three agents ---- */}
      <div style={{ position: 'absolute', inset: 0, opacity: (t > 3.0 ? 1 : 0) * (1 - wipe) }}>
        <div style={{ position: 'absolute', top: 190, left: 0, right: 0, textAlign: 'center', opacity: p(t, 3.1, 3.5) }}>
          <div style={{ fontSize: 34, fontWeight: 800, color: C.navy, letterSpacing: 6 }}>
            BLUEGECKO <span style={{ color: C.sky }}>SUITE</span>
          </div>
        </div>
        {/* flow line linking the agents */}
        <svg width={1080} height={1920} style={{ position: 'absolute' }}>
          <line x1={110} y1={420} x2={110} y2={420 + 1130 * p(t, 3.3, 4.5)} stroke={C.sky} strokeWidth={6} strokeDasharray="4 16" strokeLinecap="round" strokeDashoffset={-t * 80} />
        </svg>
        {AGENTS.map((a, i) => {
          const k = p(t, a.at, a.at + 0.6)
          const y = 330 + i * 400
          return (
            <div key={i} style={{
              position: 'absolute', left: 60, right: 60, top: y, height: 360, borderRadius: 40, background: C.white,
              boxShadow: '0 24px 70px rgba(16,32,96,0.14)', border: '2px solid #E3E9FA', overflow: 'hidden',
              transform: `translateX(${(1 - k) * 700}px) rotate(${(1 - k) * 4}deg)`, opacity: Math.min(1, k * 1.6),
            }}>
              {/* product screenshot sliding underneath */}
              <div style={{ position: 'absolute', right: -30, top: 30, width: 520, height: 300, borderRadius: 22, overflow: 'hidden', border: '2px solid #E3E9FA', boxShadow: '0 12px 30px rgba(16,32,96,0.12)', transform: 'rotate(-2deg)' }}>
                <Img src={staticFile(a.shot)} style={{ width: 1100, objectFit: 'cover', objectPosition: a.pos, transform: `translateX(${-(t - a.at) * 30}px)` }} />
                <Abs style={{ background: 'linear-gradient(90deg, rgba(255,255,255,1) 0%, rgba(255,255,255,0) 35%)' }} />
              </div>
              <Img src={staticFile(a.logo)} style={{ position: 'absolute', left: 36, top: 34, height: 190, maxWidth: 470, objectFit: 'contain', objectPosition: 'left center' }} />
              <div style={{ position: 'absolute', left: 40, bottom: 34, display: 'flex', alignItems: 'baseline', gap: 16 }}>
                <span style={{ fontSize: 64, fontWeight: 800, letterSpacing: -1.5, background: `linear-gradient(90deg, ${C.blue}, ${C.cyan})`, WebkitBackgroundClip: 'text', color: 'transparent' }}>{a.verb}</span>
                <span style={{ fontSize: 26, fontWeight: 600, color: C.muted, opacity: p(t, a.at + 0.3, a.at + 0.7) }}>{a.line}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* ---- part 3: 70% ---- */}
      <Abs style={{ background: `radial-gradient(120% 70% at 50% 40%, #12235E 0%, ${C.deep} 75%)`, clipPath: `circle(${wipe * 130}% at 50% 100%)` }}>
        <TriField t={t} seed={33} count={70} opacity={0.5} />
        <div style={{ position: 'absolute', top: 480, left: 0, right: 0, textAlign: 'center', color: C.white }}>
          <div style={{ fontSize: 34, fontWeight: 700, letterSpacing: 6, color: C.ice, opacity: p(t, 5.95, 6.35) }}>ON A LIVE MIGRATION</div>
          <div style={{ fontSize: 64, fontWeight: 700, marginTop: 60, opacity: p(t, 6.9, 7.2), transform: `translateY(${(1 - p(t, 6.9, 7.3)) * 30}px)` }}>Up to</div>
          <div style={{
            fontSize: 380, fontWeight: 800, letterSpacing: -16, lineHeight: 0.95, marginTop: 10,
            background: `linear-gradient(180deg, #FFFFFF 10%, ${C.ice} 60%, ${C.cyan})`, WebkitBackgroundClip: 'text', color: 'transparent',
            transform: `scale(${lerp(0.85, 1, p(t, 6.95, 7.5)) * (1 + 0.04 * pop(t, 8.1, 0.3) * (1 - p(t, 8.4, 8.8)))})`, opacity: p(t, 6.95, 7.2),
          }}>{pct}%</div>
          <div style={{ fontSize: 66, fontWeight: 800, marginTop: 20, opacity: p(t, 7.6, 8.0), transform: `translateY(${(1 - p(t, 7.6, 8.1)) * 30}px)` }}>less mapping effort</div>
          <div style={{ fontSize: 30, fontWeight: 500, color: '#9FB3E8', marginTop: 26, opacity: p(t, 8.3, 8.8) }}>Measured on a live migration</div>
        </div>
        <div style={{ position: 'absolute', bottom: 290, left: 0, right: 0, display: 'flex', justifyContent: 'center', opacity: p(t, 8.4, 8.9), transform: `scale(${lerp(0.9, 1, p(t, 8.4, 9.0))})` }}>
          <div style={{ background: C.white, borderRadius: 44, padding: '26px 52px', boxShadow: '0 30px 80px rgba(0,0,0,0.35)' }}>
            <Img src={staticFile('bluegecko.png')} style={{ height: 250, display: 'block' }} />
          </div>
        </div>
      </Abs>
    </Abs>
  )
}
