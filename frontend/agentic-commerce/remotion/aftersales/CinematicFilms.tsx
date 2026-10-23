import type { CSSProperties, ReactNode } from 'react'
import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion'
import {
  ArrowRight,
  Box,
  Check,
  CheckCheck,
  Network,
  Package,
  Search,
  ShoppingCart,
  Truck,
} from 'lucide-react'
import '@fontsource-variable/inter'
import aftersales from '../../film-sources/aftersales/aftersales.json'
import portal from '../../film-sources/aftersales/parts-portal.json'
import machine from '../../../src/assets/machines/nv-4500/main.webp'
import cylinder from '../../../src/assets/parts/nvm-1030-hy/main.jpg'
import working from '../../../src/assets/editorial/machinery-at-work.webp'
import service from '../../../src/assets/editorial/service.webp'
import logo from '../../../src/assets/brand/logo-reversed.png'
import {
  BusinessFlow,
  CategoriesVisual,
  EcosystemVisual,
  InstalledBaseVisual,
  OnboardingVisual,
  PortalDetailVisual,
  SystemsVisual,
} from './BusinessVisuals'

export const FILMS = { aftersales, 'parts-portal': portal }
type Film = keyof typeof FILMS
type Scene = (typeof aftersales.scenes)[number]
const INK = '#091f1c'
const TEAL = '#00bfa5'
const PAPER = '#f6f4ed'
const MUTED = '#a6bdb6'
const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const
const ease = Easing.bezier(0.2, 0.8, 0.2, 1)
const ramp = (frame: number, delay = 0, duration = 22) =>
  interpolate(frame, [delay, delay + duration], [0, 1], { ...clamp, easing: ease })

function Enter({
  children,
  delay = 0,
  style,
}: {
  children: ReactNode
  delay?: number
  style?: CSSProperties
}) {
  const frame = useCurrentFrame()
  const p = ramp(frame, delay)
  return (
    <div style={{ opacity: p, transform: `translateY(${28 * (1 - p)}px)`, ...style }}>
      {children}
    </div>
  )
}

function Label({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{ color: TEAL, fontSize: 20, fontWeight: 600, letterSpacing: 3, ...style }}>
      {children}
    </div>
  )
}

function Photo({ src, opacity = 1 }: { src: string; opacity?: number }) {
  const frame = useCurrentFrame()
  const { durationInFrames } = useVideoConfig()
  return (
    <Img
      src={src}
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        opacity,
        transform: `scale(${1.02 + (frame / durationInFrames) * 0.07})`,
      }}
    />
  )
}

function Pill({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        color: PAPER,
        border: '1px solid #45675d',
        background: '#123c34',
        padding: '18px 24px',
        borderRadius: 50,
        fontSize: 23,
        fontWeight: 500,
      }}
    >
      {children}
    </div>
  )
}

function MachineVisual() {
  const frame = useCurrentFrame()
  const p = ramp(frame, 12, 40)
  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <div
        style={{ position: 'absolute', inset: '0 0 105px 0', borderRadius: 24, overflow: 'hidden' }}
      >
        <Photo src={machine} />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(0deg,#091f1ce6,transparent 65%)',
          }}
        />
        <div style={{ position: 'absolute', left: 36, bottom: 35 }}>
          <Label>ILLUSTRATED MACHINE</Label>
          <div style={{ fontSize: 42, fontWeight: 600, marginTop: 12 }}>Wheel loader</div>
        </div>
        <svg
          width="100%"
          height="100%"
          viewBox="0 0 860 530"
          style={{ position: 'absolute', inset: 0 }}
        >
          <circle
            cx="340"
            cy="390"
            r={22 + (frame % 50) * 0.7}
            fill="none"
            stroke={TEAL}
            opacity={1 - (frame % 50) / 50}
          />
          <circle cx="340" cy="390" r="10" fill={TEAL} />
          <path
            d="M340 390 L475 305 L670 305"
            fill="none"
            stroke={TEAL}
            strokeWidth="2"
            pathLength="1"
            strokeDasharray="1"
            strokeDashoffset={1 - p}
          />
        </svg>
        <Enter delay={35} style={{ position: 'absolute', right: 30, top: 270 }}>
          <Pill>
            <Check size={24} /> Recorded fitment
          </Pill>
        </Enter>
      </div>
      <Enter
        delay={18}
        style={{
          position: 'absolute',
          bottom: 5,
          left: 0,
          right: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 20,
          fontSize: 24,
          color: MUTED,
        }}
      >
        <Search color={TEAL} size={28} /> Manufacturer <ArrowRight size={24} /> Model{' '}
        <ArrowRight size={24} /> Parts
      </Enter>
    </div>
  )
}

function JourneyVisual({ closing = false }: { closing?: boolean }) {
  const frame = useCurrentFrame()
  const steps = closing
    ? [
        { title: 'Placed', icon: ShoppingCart },
        { title: 'Allocated', icon: Box },
        { title: 'Shipped', icon: Truck },
        { title: 'Delivered', icon: CheckCheck },
      ]
    : [
        { title: 'Find', icon: Search },
        { title: 'Verify', icon: Network },
        { title: 'Review', icon: ShoppingCart },
        { title: 'Follow', icon: Truck },
      ]
  return (
    <div style={{ position: 'absolute', inset: '80px 0 0' }}>
      <Label style={{ marginBottom: 70 }}>ONE CONNECTED JOURNEY</Label>
      <div style={{ display: 'flex', justifyContent: 'space-between', position: 'relative' }}>
        <div
          style={{
            position: 'absolute',
            height: 2,
            top: 56,
            left: 55,
            right: 55,
            background: '#365a4e',
          }}
        />
        <div
          style={{
            position: 'absolute',
            height: 2,
            top: 56,
            left: 55,
            width: 680 * ramp(frame, 25, 105),
            background: TEAL,
          }}
        />
        {steps.map((step, i) => (
          <Enter key={step.title} delay={i * 22} style={{ width: 160, position: 'relative' }}>
            <div
              style={{
                width: 112,
                height: 112,
                borderRadius: 30,
                background: '#124237',
                border: '1px solid #517c69',
                display: 'grid',
                placeItems: 'center',
                marginBottom: 32,
              }}
            >
              <step.icon color={TEAL} size={40} strokeWidth={1.5} />
            </div>
            <div style={{ fontSize: 26, fontWeight: 600 }}>{step.title}</div>
            <div style={{ color: MUTED, fontSize: 18, marginTop: 12 }}>0{i + 1}</div>
          </Enter>
        ))}
      </div>
      <Enter
        delay={95}
        style={{
          marginTop: 70,
          borderTop: '1px solid #365a4e',
          paddingTop: 28,
          color: MUTED,
          fontSize: 24,
        }}
      >
        Recorded information. Clear next steps.
      </Enter>
    </div>
  )
}

function ReviewVisual() {
  return (
    <div
      style={{
        position: 'absolute',
        inset: '20px 45px 20px',
        background: PAPER,
        color: INK,
        borderRadius: 24,
        padding: '45px 50px',
        boxShadow: '0 35px 80px #0005',
      }}
    >
      <Label style={{ color: '#00756a', marginBottom: 25 }}>REVIEW BEFORE PLACING AN ORDER</Label>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24, marginBottom: 35 }}>
        <Img
          src={cylinder}
          style={{ width: 140, height: 95, objectFit: 'contain', mixBlendMode: 'multiply' }}
        />
        <div style={{ fontSize: 30, fontWeight: 600 }}>Your selected parts</div>
      </div>
      {[
        { label: 'Parts', icon: Package, sub: 'Quantity and part price' },
        { label: 'Delivery', icon: Truck, sub: 'Selected transport option' },
        { label: 'Order total', icon: CheckCheck, sub: 'Review the complete amount' },
      ].map((row, i) => (
        <Enter
          key={row.label}
          delay={20 + i * 25}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 24,
            paddingBlock: 25,
            borderTop: '1px solid #cdd7ce',
          }}
        >
          <row.icon size={32} color="#00756a" strokeWidth={1.5} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 28, fontWeight: 600 }}>{row.label}</div>
            <div style={{ fontSize: 20, color: '#56685e', marginTop: 8 }}>{row.sub}</div>
          </div>
          <Check size={26} color="#00756a" />
        </Enter>
      ))}
    </div>
  )
}

function DeliveryVisual() {
  const frame = useCurrentFrame()
  const route = ramp(frame, 20, 100)
  return (
    <div style={{ position: 'absolute', inset: '0 0 0 0' }}>
      <svg viewBox="0 0 860 640" style={{ width: '100%', height: '100%' }}>
        {Array.from({ length: 12 }, (_, i) => (
          <path
            key={i}
            d={`M0 ${i * 60} Q400 ${i * 60 - 100} 860 ${i * 60 + 30}`}
            stroke="#174239"
            strokeWidth="1"
            fill="none"
          />
        ))}
        <path
          d="M110 450 C150 450 190 450 240 350 S350 330 420 280 S600 300 740 120"
          stroke="#315c4e"
          strokeWidth="6"
          fill="none"
        />
        <path
          d="M110 450 C150 450 190 450 240 350 S350 330 420 280 S600 300 740 120"
          stroke={TEAL}
          strokeWidth="6"
          pathLength="1"
          strokeDasharray="1"
          strokeDashoffset={1 - route}
          fill="none"
        />
        {[
          [110, 450, 'Supply point'],
          [420, 280, 'Dealer / receiver'],
          [740, 120, 'Your destination'],
        ].map(([x, y, text], i) => (
          <g key={text} opacity={ramp(frame, i * 35)}>
            <circle cx={x} cy={y} r="14" fill={PAPER} stroke={TEAL} strokeWidth="5" />
            <text x={x} y={Number(y) + 55} textAnchor="middle" fontSize="22" fill={PAPER}>
              {text}
            </text>
          </g>
        ))}
      </svg>
      <Enter delay={100} style={{ position: 'absolute', bottom: 20, left: 40, right: 20 }}>
        <Pill>
          <Truck size={28} color={TEAL} /> Dispatch + travel time = delivery context
        </Pill>
      </Enter>
    </div>
  )
}

function FilmScene({ scene, film }: { scene: Scene; film: Film }) {
  const frame = useCurrentFrame()
  const full = scene.kind === 'opening' || (scene.kind === 'closing' && film === 'aftersales')
  const fade = Math.min(ramp(frame, 0, 12), ramp(scene.frames - frame, 0, 12))
  return (
    <AbsoluteFill style={{ opacity: fade }}>
      {full ? (
        <AbsoluteFill>
          <Photo src={scene.kind === 'opening' ? working : service} opacity={0.65} />
          <AbsoluteFill
            style={{
              background: 'linear-gradient(90deg,#071c18fa 0%,#071c18de 35%,#071c1855 100%)',
            }}
          />
        </AbsoluteFill>
      ) : null}
      <Enter
        style={{ position: 'absolute', top: full ? 300 : 245, left: 95, width: full ? 1300 : 765 }}
      >
        <Label>{scene.eyebrow}</Label>
        <h1
          style={{
            fontSize: full ? 108 : 88,
            lineHeight: 1.08,
            fontWeight: 550,
            letterSpacing: -5,
            whiteSpace: 'pre-line',
            margin: '30px 0 38px',
            textWrap: 'balance',
          }}
        >
          {scene.title}
        </h1>
        <div style={{ width: 85 + 95 * ramp(frame, 15, 40), height: 4, background: TEAL }} />
        {full ? (
          <Enter
            delay={42}
            style={{
              marginTop: 45,
              display: 'flex',
              gap: 20,
              alignItems: 'center',
              color: MUTED,
              fontSize: 28,
            }}
          >
            {film === 'aftersales'
              ? scene.kind === 'opening'
                ? 'Manufacturer. Dealer. Customer. A lifetime of service.'
                : 'Parts availability. Service continuity. Customer trust.'
              : 'Find. Check. Order. One Parts Portal.'}{' '}
            <ArrowRight size={28} color={TEAL} />
          </Enter>
        ) : null}
      </Enter>
      {!full ? (
        <Enter
          delay={8}
          style={{ position: 'absolute', top: 205, left: 965, width: 860, height: 640 }}
        >
          {scene.kind === 'ecosystem' ? (
            <EcosystemVisual />
          ) : scene.kind === 'onboarding' ? (
            <OnboardingVisual />
          ) : scene.kind === 'systems' ? (
            <SystemsVisual />
          ) : scene.kind === 'business-data' ? (
            <InstalledBaseVisual />
          ) : scene.kind === 'parts-flow' ||
            scene.kind === 'service-flow' ||
            scene.kind === 'warranty' ? (
            <BusinessFlow kind={scene.kind} />
          ) : scene.kind === 'catalogue' ? (
            <CategoriesVisual />
          ) : scene.kind === 'portal-detail' ? (
            <PortalDetailVisual />
          ) : scene.kind === 'machine' ? (
            <MachineVisual />
          ) : scene.kind === 'review' ? (
            <ReviewVisual />
          ) : scene.kind === 'delivery' ? (
            <DeliveryVisual />
          ) : (
            <JourneyVisual closing={scene.kind === 'closing'} />
          )}
        </Enter>
      ) : null}
    </AbsoluteFill>
  )
}

export function CinematicFilm({
  film,
  burnCaptions = false,
}: {
  film: Film
  burnCaptions?: boolean
}) {
  const frame = useCurrentFrame()
  const data = FILMS[film]
  const seconds = frame / data.fps
  const caption = data.captions.find((c) => seconds >= c.start && seconds < c.end)
  return (
    <AbsoluteFill
      style={{
        background: INK,
        color: PAPER,
        fontFamily: "'Inter Variable', Inter, sans-serif",
        overflow: 'hidden',
      }}
    >
      {data.scenes.map((scene, i) => (
        <Sequence
          key={scene.eyebrow}
          from={Math.round(scene.start * data.fps)}
          durationInFrames={scene.frames}
        >
          <FilmScene scene={scene} film={film} />
          <Sequence from={Math.round(0.55 * data.fps)} layout="none">
            <Audio src={staticFile(scene.audio)} volume={1} />
          </Sequence>
          <div
            style={{
              position: 'absolute',
              top: 76,
              right: 95,
              color: MUTED,
              fontSize: 22,
              letterSpacing: 2,
            }}
          >
            {String(i + 1).padStart(2, '0')}{' '}
            <span style={{ color: '#536f64' }}>
              / {String(data.scenes.length).padStart(2, '0')}
            </span>
          </div>
        </Sequence>
      ))}
      <Audio src={staticFile(`${film}/music.mp3`)} volume={0.1} />
      <Img
        src={logo}
        style={{
          position: 'absolute',
          top: 55,
          left: 95,
          width: 260,
          height: 73,
          objectFit: 'contain',
        }}
      />
      <div
        style={{
          position: 'absolute',
          top: 152,
          left: 95,
          right: 95,
          height: 1,
          background: '#ffffff24',
        }}
      />
      {burnCaptions && caption ? (
        <div
          style={{ position: 'absolute', bottom: 85, left: 230, right: 230, textAlign: 'center' }}
        >
          <span
            style={{
              display: 'inline-block',
              background: '#061913e8',
              borderRadius: 10,
              padding: '14px 24px',
              fontSize: 29,
              lineHeight: 1.4,
              color: '#fff',
              maxWidth: 1400,
            }}
          >
            {caption.text}
          </span>
        </div>
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: 95,
          bottom: 35,
          fontSize: 17,
          color: MUTED,
          letterSpacing: 0.5,
        }}
      >
        {film === 'aftersales'
          ? 'Aftersales operating model Â· illustrative business processes'
          : 'Parts Portal walkthrough Â· demonstration catalogue and supply data'}
      </div>
      <div style={{ position: 'absolute', right: 95, bottom: 35, color: MUTED, fontSize: 17 }}>
        NOORDVELD MACHINERY B.V.
      </div>
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          height: 4,
          background: TEAL,
          width: `${(frame / (data.frames - 1)) * 100}%`,
        }}
      />
    </AbsoluteFill>
  )
}
