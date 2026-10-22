import React from 'react'
import { Img, staticFile, useCurrentFrame } from 'remotion'
import { Abs, C, FONT, inE, lerp, p, pop } from '../lib'

const STOP = 0.85
const AMBER = '#FFA21A'

/** Downtime clock: mm:ss.cc since the loader stopped. */
const downtime = (t: number) => {
  const s = Math.max(0, t - STOP)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}.${String(Math.floor((s * 100) % 100)).padStart(2, '0')}`
}

// ---------- telemetry line: hydraulic pressure, written from the right, flatlines at STOP ----------
const HEAD_X = 860
const SPEED = 520 // px per second
const signal = (time: number) =>
  Math.sin(time * 9) * 22 + Math.sin(time * 23 + 1) * 9 + Math.max(0, Math.sin(time * 4.2)) ** 18 * -120

const Telemetry: React.FC<{ t: number; y: number; dim: number }> = ({ t, y, dim }) => {
  const pre: string[] = []
  const post: string[] = []
  for (let x = -10; x <= HEAD_X; x += 5) {
    const at = t - (HEAD_X - x) / SPEED
    const dead = at > STOP
    const v = dead ? lerp(0, 70, p(at, STOP, STOP + 0.18)) + Math.sin((at - STOP) * 40) * 6 * Math.exp(-(at - STOP) * 8) : signal(at)
    ;(dead ? post : pre).push(`${x},${(y + v).toFixed(1)}`)
  }
  if (post.length && pre.length) post.unshift(pre[pre.length - 1])
  const headDead = t > STOP
  const headY = headDead ? y + 70 : y + signal(t)
  return (
    <svg width={1080} height={1920} style={{ position: 'absolute', inset: 0, opacity: 1 - dim * 0.7 }}>
      <defs>
        <linearGradient id="fadeL" x1="0" x2="1">
          <stop offset="0" stopColor="white" stopOpacity="0" />
          <stop offset="0.35" stopColor="white" stopOpacity="1" />
        </linearGradient>
        <mask id="tm"><rect width={1080} height={1920} fill="url(#fadeL)" /></mask>
        <filter id="glow" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="6" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      {[-140, -70, 0, 70, 140].map((d) => <line key={d} x1={0} x2={1080} y1={y + d} y2={y + d} stroke="#2E8BEF" strokeOpacity={d === 0 ? 0.14 : 0.06} strokeDasharray={d === 0 ? '0' : '2 10'} />)}
      <g mask="url(#tm)" filter="url(#glow)">
        {pre.length > 1 && <polyline points={pre.join(' ')} fill="none" stroke={C.cyan} strokeWidth={4} strokeLinejoin="round" />}
        {post.length > 1 && <polyline points={post.join(' ')} fill="none" stroke={C.red} strokeWidth={4} strokeLinejoin="round" />}
      </g>
      <circle cx={HEAD_X} cy={headY} r={9} fill={headDead ? C.red : C.cyan} filter="url(#glow)" />
      <circle cx={HEAD_X} cy={headY} r={22 + Math.sin(t * 12) * 4} fill="none" stroke={headDead ? C.red : C.cyan} strokeOpacity={0.4} strokeWidth={2} />
      <text x={HEAD_X + 34} y={headY + 10} fontFamily={FONT} fontWeight={800} fontSize={34} fill={headDead ? '#FF9AA5' : C.white}>
        {Math.round(headDead ? lerp(210, 0, p(t, STOP, STOP + 0.5)) : 204 + signal(t) * -0.1)}
      </text>
      <text x={HEAD_X + 34} y={headY + 40} fontFamily={FONT} fontWeight={600} fontSize={18} fill="#8FA3D9" letterSpacing={3}>BAR</text>
    </svg>
  )
}

/** Animated film grain. */
const Grain: React.FC = () => {
  const frame = useCurrentFrame()
  return (
    <svg width={1080} height={1920} style={{ position: 'absolute', inset: 0, opacity: 0.09, mixBlendMode: 'overlay', pointerEvents: 'none' }}>
      <filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={frame % 97} /><feColorMatrix type="saturate" values="0" /></filter>
      <rect width={1080} height={1920} filter="url(#grain)" />
    </svg>
  )
}

/** Words that rise out of a mask and sharpen from a blur. */
const Kinetic: React.FC<{ t: number; at: number; text: string; size: number; color?: string; step?: number; style?: React.CSSProperties }> = ({
  t, at, text, size, color = C.white, step = 0.08, style,
}) => (
  <div style={{ display: 'flex', justifyContent: 'center', columnGap: size * 0.24, fontSize: size, fontWeight: 800, letterSpacing: -size * 0.045, lineHeight: 1, color, ...style }}>
    {text.split(' ').map((w, i) => {
      const k = p(t, at + i * step, at + i * step + 0.7)
      return (
        <span key={i} style={{ display: 'inline-block', overflow: 'hidden', padding: '0.06em 0.02em 0.12em' }}>
          <span style={{ display: 'inline-block', transform: `translateY(${(1 - k) * 100}%)`, filter: `blur(${(1 - k) * 14}px)`, opacity: k > 0 ? 1 : 0 }}>{w}</span>
        </span>
      )
    })}
  </div>
)

const Kicker: React.FC<{ k: number; color?: string; children: React.ReactNode; style?: React.CSSProperties }> = ({ k, color = '#8FA3D9', children, style }) => (
  <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: 7, color, opacity: k, transform: `translateY(${(1 - k) * 12}px)`, textAlign: 'center', ...style }}>{children}</div>
)

const CATALOGUES = [
  { title: 'Catalogue 2014', file: 'parts_catalogue_2014.pdf' },
  { title: 'Supplier list', file: 'supplier_xref_v7.xlsx' },
  { title: 'Legacy ERP', file: 'AS/400 · ITEMMAST' },
]

/** 0–8s: premium kinetic type. Telemetry flatlines, "A machine is down.", the discontinued part, three catalogues, no match. */
export const Opening: React.FC<{ t: number }> = ({ t }) => {
  const stopped = p(t, STOP, STOP + 0.15)
  const pulse = 0.55 + 0.45 * Math.cos((t - STOP) * Math.PI * 2.4)
  const flash = t > STOP ? Math.max(0, 1 - (t - STOP) / 0.18) : 0
  const shake = t > STOP ? Math.sin(t * 95) * 10 * Math.exp(-(t - STOP) * 7) : 0
  const b1 = 1 - p(t, 2.6, 3.0, inE)
  const b2in = p(t, 3.0, 3.6)
  const b2out = p(t, 4.85, 5.2, inE)
  const b3 = p(t, 5.0, 5.4)
  const strike = p(t, 3.95, 4.25)
  const sweep = lerp(-30, 110, p(t, 3.3, 4.3, (x) => x))
  const out = p(t, 7.55, 8.0, inE)

  return (
    <Abs style={{ fontFamily: FONT, background: 'radial-gradient(90% 60% at 50% 50%, #0C1A4E 0%, #060C2B 55%, #02040F 100%)', overflow: 'hidden' }}>
      {/* ---------- beat 1: running -> stopped ---------- */}
      <Abs style={{ opacity: b1, transform: `translateX(${shake}px)` }}>
        {/* amber warning glow + anamorphic streak */}
        <Abs style={{ opacity: stopped, background: `radial-gradient(38% 22% at 50% 50%, rgba(255,162,26,${0.38 * pulse}) 0%, rgba(255,120,20,${0.12 * pulse}) 45%, transparent 75%)` }} />
        <div style={{
          position: 'absolute', left: -100, right: -100, top: 958, height: 4, opacity: stopped * (0.4 + 0.6 * pulse),
          background: `linear-gradient(90deg, transparent, ${AMBER} 35%, #FFE7B8 50%, ${AMBER} 65%, transparent)`, boxShadow: `0 0 40px 10px rgba(255,162,26,${0.5 * pulse})`,
        }} />
        <Telemetry t={t} y={1360} dim={stopped * 0.4} />

        <div style={{ position: 'absolute', top: 180, left: 70, right: 70, display: 'flex', justifyContent: 'space-between', alignItems: 'center', opacity: p(t, 0.1, 0.4) }}>
          <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: 6, color: '#8FA3D9' }}>NV-4500 · WHEEL LOADER</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 28, fontWeight: 800, letterSpacing: 5, color: t > STOP ? '#FF9AA5' : '#7EF0C8' }}>
            <span style={{ width: 14, height: 14, borderRadius: 7, background: t > STOP ? C.red : C.green, boxShadow: `0 0 16px ${t > STOP ? C.red : C.green}`, opacity: t > STOP && Math.floor(t * 4) % 2 ? 0.35 : 1 }} />
            {t > STOP ? 'STOPPED' : 'LIVE'}
          </div>
        </div>

        <div style={{ position: 'absolute', top: 730, left: 0, right: 0 }}>
          <Kinetic t={t} at={0.6} text="A machine" size={176} />
          <Kinetic t={t} at={0.86} text="is down." size={176} style={{ marginTop: -6 }} />
        </div>
        <div style={{ position: 'absolute', top: 1130, left: 0, right: 0, textAlign: 'center', opacity: p(t, STOP + 0.25, STOP + 0.6) }}>
          <Kicker k={1} color="#FF9AA5">DOWNTIME</Kicker>
          <div style={{ fontSize: 64, fontWeight: 300, color: C.white, fontVariantNumeric: 'tabular-nums', letterSpacing: 2, marginTop: 6 }}>{downtime(t)}</div>
        </div>
      </Abs>
      <Abs style={{ background: `rgba(255,190,90,${flash * 0.35})` }} />

      {/* ---------- beat 2: the part ---------- */}
      {t > 2.9 && t < 5.3 && (
        <Abs style={{ opacity: b2in * (1 - b2out), transform: `translateY(${-b2out * 120}px) scale(${lerp(1, 0.92, b2out)})` }}>
          <div style={{ position: 'absolute', top: 640, left: 0, right: 0, textAlign: 'center', fontSize: 300, fontWeight: 800, letterSpacing: -14, color: 'transparent', WebkitTextStroke: '2px rgba(124,211,247,0.14)', transform: `translateX(${lerp(60, -60, p(t, 3, 5.2, (x) => x))}px)` }}>AS-411-C</div>
          <div style={{ position: 'absolute', top: 330, left: 0, right: 0 }}>
            <Kicker k={p(t, 3.15, 3.5)} color={C.ice}>OEM PART · TILT CYLINDER</Kicker>
            <div style={{ position: 'relative', width: 'fit-content', margin: '18px auto 0' }}>
              <Kinetic t={t} at={3.2} text="AS-411-C" size={140} style={{ opacity: lerp(1, 0.45, strike) }} />
              <div style={{ position: 'absolute', left: -20, right: -20, top: '54%', height: 10, borderRadius: 5, background: C.red, transform: `scaleX(${strike})`, transformOrigin: '0% 50%', boxShadow: '0 0 30px rgba(255,77,94,0.7)' }} />
            </div>
          </div>
          {/* the part, lit */}
          <div style={{ position: 'absolute', left: 90, top: 820, width: 900, transform: `translateX(${lerp(90, -20, p(t, 3.0, 5.2))}px) scale(${lerp(0.94, 1.04, p(t, 3.0, 5.2, (x) => x))})` }}>
            <div style={{ position: 'absolute', left: 80, right: 80, top: 230, height: 90, borderRadius: '50%', background: 'radial-gradient(closest-side, rgba(46,139,239,0.45), transparent)', filter: 'blur(10px)' }} />
            <Img src={staticFile('tiltcyl-cut.png')} style={{ width: 900, display: 'block', position: 'relative', filter: 'drop-shadow(0 0 28px rgba(46,139,239,0.35)) contrast(1.06)' }} />
            <div style={{
              position: 'absolute', inset: 0, WebkitMaskImage: `url(${staticFile('tiltcyl-cut.png')})`, WebkitMaskSize: '100% 100%',
              background: `linear-gradient(105deg, transparent ${sweep - 12}%, rgba(255,255,255,0.55) ${sweep}%, transparent ${sweep + 12}%)`, mixBlendMode: 'screen',
            }} />
          </div>
          <div style={{ position: 'absolute', top: 1150, left: 0, right: 0, transform: `translateX(${t > 3.95 && t < 4.3 ? Math.sin(t * 80) * 8 : 0}px)` }}>
            <Kinetic t={t} at={3.95} text="Discontinued." size={104} color="#FF6B7A" />
          </div>
        </Abs>
      )}

      {/* ---------- beat 3: three catalogues, no match ---------- */}
      {t > 4.95 && (
        <Abs style={{ opacity: b3 }}>
          <div style={{ position: 'absolute', top: 300, left: 0, right: 0 }}>
            <Kicker k={p(t, 5.0, 5.3)}>SEARCHING</Kicker>
            <Kinetic t={t} at={5.05} text="3 catalogues" size={118} style={{ marginTop: 14 }} />
          </div>
          {CATALOGUES.map((c, i) => {
            const at = 5.15 + i * 0.22
            const k = p(t, at, at + 0.5)
            const scan = p(t, at + 0.25, 5.5 + i * 0.5, (x) => x)
            const fail = pop(t, 5.5 + i * 0.5, 0.35)
            return (
              <div key={i} style={{
                position: 'absolute', left: 90, right: 90, top: 600 + i * 196, height: 168, borderRadius: 30,
                background: fail > 0 ? 'rgba(255,77,94,0.08)' : 'rgba(255,255,255,0.05)', border: `1.5px solid ${fail > 0 ? 'rgba(255,77,94,0.45)' : 'rgba(255,255,255,0.12)'}`,
                transform: `translateX(${(1 - k) * 140}px)`, opacity: k, display: 'flex', alignItems: 'center', padding: '0 36px', gap: 28, overflow: 'hidden', boxSizing: 'border-box',
              }}>
                <svg width={64} height={78} style={{ flexShrink: 0 }}>
                  <path d="M 6 4 L 44 4 L 60 20 L 60 74 L 6 74 Z" fill="rgba(124,211,247,0.12)" stroke={C.ice} strokeWidth={3} />
                  {[30, 42, 54].map((y) => <line key={y} x1={16} x2={50} y1={y} y2={y} stroke={C.ice} strokeOpacity={0.6} strokeWidth={3} />)}
                </svg>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 40, fontWeight: 800, color: C.white }}>{c.title}</div>
                  <div style={{ fontSize: 24, fontWeight: 500, color: '#8FA3D9', marginTop: 4 }}>{c.file}</div>
                </div>
                <div style={{ width: 230, textAlign: 'right' }}>
                  {fail > 0 ? (
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 12, transform: `scale(${fail})`, transformOrigin: '100% 50%' }}>
                      <span style={{ fontSize: 30, fontWeight: 800, color: '#FF9AA5' }}>0 matches</span>
                      <svg width={40} height={40}><circle cx={20} cy={20} r={20} fill={C.red} /><path d="M 13 13 L 27 27 M 27 13 L 13 27" stroke="white" strokeWidth={4.5} strokeLinecap="round" /></svg>
                    </div>
                  ) : (
                    <div style={{ height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
                      <div style={{ width: `${scan * 100}%`, height: '100%', background: C.cyan, boxShadow: `0 0 12px ${C.cyan}` }} />
                    </div>
                  )}
                </div>
                {fail <= 0 && scan > 0 && <div style={{ position: 'absolute', top: 0, bottom: 0, width: 160, left: `${scan * 100}%`, marginLeft: -160, background: 'linear-gradient(90deg, transparent, rgba(34,184,232,0.18), transparent)' }} />}
              </div>
            )
          })}
          <div style={{ position: 'absolute', top: 1235, left: 0, right: 0 }}>
            <Kinetic t={t} at={6.55} text="No match." size={150} color="#FF6B7A" />
          </div>
        </Abs>
      )}

      {/* downtime keeps counting (beats 2–3) */}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 1500, display: 'flex', justifyContent: 'center', opacity: p(t, 3.0, 3.4) * (1 - out) }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 14, padding: '12px 26px', borderRadius: 999, border: '1.5px solid rgba(255,77,94,0.35)', background: 'rgba(255,77,94,0.06)', fontSize: 26, fontWeight: 600, letterSpacing: 2, color: '#FFB3BB' }}>
          <span style={{ width: 12, height: 12, borderRadius: 6, background: C.red, opacity: Math.floor(t * 4) % 2 ? 1 : 0.3 }} />
          DOWNTIME <span style={{ fontVariantNumeric: 'tabular-nums', color: C.white, fontWeight: 300, fontSize: 30 }}>{downtime(t)}</span>
        </div>
      </div>

      {/* vignette + grain */}
      <Abs style={{ background: 'radial-gradient(80% 60% at 50% 50%, transparent 55%, rgba(0,0,0,0.6) 100%)', pointerEvents: 'none' }} />
      <Grain />

      {/* exit: white iris into the YOA scene */}
      <Abs style={{ background: C.bg, clipPath: `circle(${out * 120}% at 50% 50%)` }} />
    </Abs>
  )
}
