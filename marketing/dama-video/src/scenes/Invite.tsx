import React from 'react'
import { Img, staticFile } from 'remotion'
import { Abs, C, FONT, inOutE, lerp, p, pop } from '../lib'

const Row: React.FC<{ icon: React.ReactNode; children: React.ReactNode; k: number }> = ({ icon, children, k }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 22, opacity: k, transform: `translateY(${(1 - k) * 24}px)` }}>
    <div style={{ width: 64, height: 64, borderRadius: 18, background: '#EEF2FB', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{icon}</div>
    <div style={{ fontSize: 38, fontWeight: 700, color: C.ink }}>{children}</div>
  </div>
)

/** 27–33s: the 9th-floor view at sunset, then the event card. */
export const Invite: React.FC<{ t: number }> = ({ t }) => {
  const cut = p(t, 1.15, 1.6, inOutE) // push from the tower into the 9th-floor lounge
  const card = p(t, 2.85, 3.45)
  const blur = p(t, 2.8, 3.4)
  const lin = (x: number) => x

  return (
    <Abs style={{ fontFamily: FONT, background: C.deep, overflow: 'hidden' }}>
      {/* The Sheryl from outside at sunset (b-events.amsterdam) */}
      <Abs style={{ opacity: 1 - cut, transform: `scale(${lerp(1.0, 1.06, p(t, 0, 1.6, lin)) * (1 + cut * 0.5)})`, filter: `blur(${cut * 10}px)` }}>
        <Img src={staticFile('sheryl-drone.jpg')} style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: `${lerp(84, 52, p(t, 0, 1.6, (x) => x * (2 - x)))}% 50%` }} />
      </Abs>
      {/* The Sheryl lounge, panoramic windows */}
      <Abs style={{ opacity: cut, transform: `scale(${lerp(1.25, 1.04, cut) * lerp(1, 1.04, p(t, 1.6, 6, lin))})`, filter: `blur(${blur * 16}px) brightness(${1 - blur * 0.35})` }}>
        <Img src={staticFile('sheryl-lounge.jpg')} style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: `${lerp(18, 58, p(t, 1.15, 6, lin))}% 50%` }} />
      </Abs>
      <Abs style={{ background: 'linear-gradient(180deg, rgba(5,11,36,0) 45%, rgba(5,11,36,0.85) 100%)' }} />

      {/* sunset title */}
      <div style={{ position: 'absolute', left: 70, right: 70, bottom: 470, color: C.white, opacity: 1 - card }}>
        <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: 6, color: '#FFD3A8', opacity: p(t, 0.2, 0.6) }}>LIVE · THU 29 OCTOBER</div>
        <div style={{ fontSize: 110, fontWeight: 800, letterSpacing: -3, lineHeight: 1, marginTop: 14, transform: `translateY(${(1 - p(t, 0.3, 0.9)) * 40}px)`, opacity: p(t, 0.3, 0.8) }}>
          See both, live.
        </div>
        <div style={{ fontSize: 48, fontWeight: 700, marginTop: 18, opacity: p(t, 1.45, 1.85), transform: `translateY(${(1 - p(t, 1.45, 1.95)) * 24}px)` }}>9th floor · B. Amsterdam</div>
      </div>

      {/* tagline above the card */}
      <div style={{ position: 'absolute', top: 150, left: 0, right: 0, textAlign: 'center', color: C.white, fontSize: 44, fontWeight: 700, opacity: p(t, 4.2, 4.6), transform: `translateY(${(1 - p(t, 4.2, 4.7)) * 20}px)` }}>
        The view and the drinks are on us.
      </div>

      {/* event card */}
      <div style={{
        position: 'absolute', left: 60, right: 60, top: 250, height: 1370, borderRadius: 48, background: C.white,
        boxShadow: '0 50px 140px rgba(0,0,0,0.45)', padding: '60px 64px', boxSizing: 'border-box',
        transform: `translateY(${(1 - card) * 1800}px) rotate(${(1 - card) * -4}deg)`,
      }}>
        <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: 5, color: C.blue }}>YOU'RE INVITED</div>
        <div style={{ fontSize: 92, fontWeight: 800, color: C.ink, letterSpacing: -3, lineHeight: 1.0, marginTop: 14 }}>DAMA Drinks<br />Amsterdam</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, marginTop: 40 }}>
          <Row k={p(t, 3.05, 3.45)} icon={
            <svg width={34} height={34}><rect x={3} y={6} width={28} height={25} rx={5} fill="none" stroke={C.blue} strokeWidth={3.5} /><line x1={3} y1={14} x2={31} y2={14} stroke={C.blue} strokeWidth={3.5} /><line x1={11} y1={2} x2={11} y2={9} stroke={C.blue} strokeWidth={3.5} /><line x1={23} y1={2} x2={23} y2={9} stroke={C.blue} strokeWidth={3.5} /></svg>
          }>Thu 29 Oct · 17:30</Row>
          <Row k={p(t, 3.15, 3.55)} icon={
            <svg width={34} height={34}><path d="M17 32 C 8 21 5 16 5 12 a12 12 0 0 1 24 0 c0 4-3 9-12 20z" fill="none" stroke={C.blue} strokeWidth={3.5} /><circle cx={17} cy={12} r={4} fill={C.blue} /></svg>
          }>The Sheryl, B. Amsterdam</Row>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 34, marginTop: 44, paddingTop: 36, borderTop: '2px solid #EEF2FB', opacity: p(t, 3.25, 3.65) }}>
          <Img src={staticFile('dama.png')} style={{ height: 120 }} />
          <div style={{ fontSize: 50, fontWeight: 300, color: C.muted }}>×</div>
          <Img src={staticFile('ngl-logo.png')} style={{ height: 110 }} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 44, marginTop: 40 }}>
          <div style={{ transform: `scale(${pop(t, 3.3, 0.5)})`, transformOrigin: '50% 50%' }}>
            <Img src={staticFile('qr.png')} style={{ height: 470 }} />
          </div>
          <div style={{ opacity: p(t, 3.55, 3.95) }}>
            <div style={{ fontSize: 46, fontWeight: 800, color: C.ink, lineHeight: 1.1 }}>Scan to<br />register</div>
            <div style={{ fontSize: 26, color: C.muted, marginTop: 16, lineHeight: 1.35 }}>Register on Eventbrite<br />DAMA Nederland ×<br />Nextgenlytics</div>
          </div>
        </div>
      </div>
    </Abs>
  )
}
