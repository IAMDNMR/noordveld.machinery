import type { CSSProperties, ReactNode } from 'react'
import { Img, interpolate, useCurrentFrame } from 'remotion'
import {
  ArrowLeftRight,
  Building2,
  Check,
  ClipboardList,
  Cog,
  Database,
  FileCheck,
  Filter,
  GraduationCap,
  Handshake,
  Layers,
  Package,
  ShieldCheck,
  SlidersHorizontal,
  Snowflake,
  Truck,
  Users,
  Wrench,
  Zap,
  Droplets,
  CircleDot,
} from 'lucide-react'
import bucket from '../../../src/assets/parts/nvm-1010-at/main.jpg'
import story from '../../film-sources/aftersales/story.json'

const TEAL = '#00bfa5'
const INK = '#091f1c'
const PAPER = '#f6f4ed'
const MUTED = '#a6bdb6'
const border = '1px solid #36594e'
const progress = (f: number, delay = 0, frames = 24) =>
  interpolate(f, [delay, delay + frames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  })
function Reveal({
  children,
  delay = 0,
  style,
}: {
  children: ReactNode
  delay?: number
  style?: CSSProperties
}) {
  const p = progress(useCurrentFrame(), delay)
  return (
    <div style={{ opacity: p, transform: `translateY(${18 * (1 - p)}px)`, ...style }}>
      {children}
    </div>
  )
}
function Small({ children, light = false }: { children: ReactNode; light?: boolean }) {
  return (
    <div
      style={{ fontSize: 19, letterSpacing: 2, color: light ? '#00756a' : TEAL, fontWeight: 600 }}
    >
      {children}
    </div>
  )
}

export function EcosystemVisual() {
  const actors = [
    {
      name: 'Manufacturer / OEM',
      icon: Building2,
      detail: 'Product knowledge · parts · warranty policy',
    },
    {
      name: 'Independent dealer',
      icon: Wrench,
      detail: 'Local stock · technicians · customer support',
    },
    { name: 'Machine owner', icon: Users, detail: 'Machine use · maintenance needs · feedback' },
  ]
  return (
    <div style={{ padding: '25px 20px' }}>
      <Small>RESPONSIBILITIES ACROSS THE NETWORK</Small>
      {actors.map((actor, i) => (
        <Reveal key={actor.name} delay={i * 35 + 10}>
          <div
            style={{
              display: 'flex',
              gap: 28,
              alignItems: 'center',
              paddingBlock: 26,
              borderBottom: border,
            }}
          >
            <div
              style={{
                width: 90,
                height: 90,
                flexShrink: 0,
                borderRadius: '50%',
                background: '#164438',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <actor.icon size={38} color={TEAL} strokeWidth={1.5} />
            </div>
            <div>
              <div style={{ fontSize: 31, fontWeight: 550 }}>{actor.name}</div>
              <div style={{ fontSize: 22, lineHeight: 1.5, marginTop: 12, color: MUTED }}>
                {actor.detail}
              </div>
            </div>
          </div>
          {i < 2 ? (
            <ArrowLeftRight
              size={27}
              color={TEAL}
              style={{ margin: '15px 0 0 30px', transform: 'rotate(90deg)' }}
            />
          ) : null}
        </Reveal>
      ))}
    </div>
  )
}

export function OnboardingVisual() {
  const steps = [
    {
      title: 'Business & agreements',
      detail: 'Dealer profile, responsibilities and commercial terms',
      icon: Handshake,
    },
    {
      title: 'Access & permissions',
      detail: 'Authorised users, roles and product access',
      icon: ShieldCheck,
    },
    {
      title: 'Knowledge & training',
      detail: 'Catalogue, technical information and claims guidance',
      icon: GraduationCap,
    },
    {
      title: 'Connection & validation',
      detail: 'Map data, test exchange and resolve exceptions',
      icon: Database,
    },
  ]
  return (
    <div style={{ background: PAPER, color: INK, borderRadius: 24, padding: '35px 40px' }}>
      <Small light>A TYPICAL DEALER ONBOARDING FLOW</Small>
      {steps.map((step, i) => (
        <Reveal
          key={step.title}
          delay={15 + i * 40}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 23,
            paddingBlock: 26,
            borderBottom: '1px solid #cfd9cf',
          }}
        >
          <step.icon size={32} color="#00756a" style={{ flexShrink: 0 }} strokeWidth={1.5} />
          <div>
            <div style={{ fontSize: 27, fontWeight: 600 }}>{step.title}</div>
            <div style={{ fontSize: 20, color: '#56685e', lineHeight: 1.4, marginTop: 8 }}>
              {step.detail}
            </div>
          </div>
        </Reveal>
      ))}
      <Reveal
        delay={170}
        style={{
          display: 'flex',
          gap: 14,
          alignItems: 'center',
          marginTop: 25,
          color: '#00756a',
          fontSize: 22,
        }}
      >
        <Check size={25} /> Ready to participate in the network
      </Reveal>
    </div>
  )
}

export function SystemsVisual() {
  return (
    <div style={{ paddingTop: 30 }}>
      <Small>TWO SYSTEMS. A SHARED BUSINESS PROCESS.</Small>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 90px 1fr',
          alignItems: 'center',
          marginTop: 40,
        }}
      >
        {[
          {
            title: 'OEM portal',
            icon: Building2,
            rows: [
              'Parts & orders',
              'Warranty claims',
              'Technical documents',
              'Dealer information',
            ],
          },
          {
            title: 'Dealer system',
            icon: Wrench,
            rows: ['Local inventory', 'Workshop jobs', 'Customer records', 'Finance & sales'],
          },
        ].map((system, i) => (
          <Reveal
            key={system.title}
            delay={20 + i * 25}
            style={{
              gridColumn: i ? 3 : 1,
              gridRow: 1,
              border,
              borderRadius: 24,
              padding: '32px 26px',
              background: i ? '#143c32' : '#0e2e27',
            }}
          >
            <system.icon size={36} color={TEAL} strokeWidth={1.5} />
            <div style={{ fontSize: 30, fontWeight: 600, marginTop: 20, marginBottom: 24 }}>
              {system.title}
            </div>
            {system.rows.map((row) => (
              <div key={row} style={{ borderTop: border, paddingBlock: 18, fontSize: 21 }}>
                {row}
              </div>
            ))}
          </Reveal>
        ))}
        <Reveal delay={75} style={{ gridColumn: 2, gridRow: 1, textAlign: 'center' }}>
          <ArrowLeftRight size={42} color={TEAL} />
        </Reveal>
      </div>
      <Reveal delay={105} style={{ textAlign: 'center', marginTop: 38 }}>
        <div style={{ color: TEAL, fontSize: 24 }}>Interfaces + shared data definitions</div>
        <div style={{ color: MUTED, fontSize: 21, marginTop: 15 }}>
          Customer · machine · parts · service · claims
        </div>
      </Reveal>
    </div>
  )
}

const flows = {
  'parts-flow': {
    label: 'PARTS: DEMAND TO SUPPLY',
    rows: [
      {
        title: 'Identify the correct part',
        sub: 'Machine identity, component and compatibility',
        icon: Package,
      },
      {
        title: 'Check supply & place the order',
        sub: 'Stock, replenishment and back orders',
        icon: ClipboardList,
      },
      {
        title: 'Deliver to the right location',
        sub: 'Dealer, workshop or customer site',
        icon: Truck,
      },
      {
        title: 'Handle returns & update stock',
        sub: 'Return authorisation and inventory records',
        icon: ArrowLeftRight,
      },
    ],
  },
  'service-flow': {
    label: 'SERVICE: ISSUE TO REPAIR HISTORY',
    rows: [
      {
        title: 'Record & diagnose',
        sub: 'Machine details, symptoms and fault evidence',
        icon: ClipboardList,
      },
      { title: 'Plan the job', sub: 'Parts, technician capacity and appointment', icon: Users },
      {
        title: 'Complete the repair',
        sub: 'Workshop work or service at the customer site',
        icon: Wrench,
      },
      {
        title: 'Record the outcome',
        sub: 'Labour, replaced parts and machine service history',
        icon: FileCheck,
      },
    ],
  },
  warranty: {
    label: 'WARRANTY: CLAIM TO RECORDED OUTCOME',
    rows: [
      {
        title: 'Dealer submits the claim',
        sub: 'Machine identity, repair details, parts and labour',
        icon: ClipboardList,
      },
      {
        title: 'Review the evidence',
        sub: 'Eligibility and the applicable warranty terms',
        icon: ShieldCheck,
      },
      {
        title: 'Approve, query or decline',
        sub: 'A recorded decision with a clear reason',
        icon: FileCheck,
      },
      {
        title: 'Reimburse approved work',
        sub: 'Dealer credit and a complete claim history',
        icon: ArrowLeftRight,
      },
    ],
  },
}

export function BusinessFlow({ kind }: { kind: keyof typeof flows }) {
  const flow = flows[kind]
  const frame = useCurrentFrame()
  return (
    <div style={{ padding: '25px 20px' }}>
      <Small>{flow.label}</Small>
      <div style={{ position: 'relative', marginTop: 35 }}>
        <div
          style={{
            position: 'absolute',
            left: 31,
            top: 35,
            width: 2,
            height: 420,
            background: '#36594e',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: 31,
            top: 35,
            width: 2,
            height: progress(frame, 20, 145) * 420,
            background: TEAL,
          }}
        />
        {flow.rows.map((row, i) => (
          <Reveal
            key={row.title}
            delay={20 + i * 40}
            style={{ display: 'flex', gap: 28, minHeight: 140, position: 'relative' }}
          >
            <div
              style={{
                width: 64,
                height: 64,
                flexShrink: 0,
                display: 'grid',
                placeItems: 'center',
                borderRadius: '50%',
                border,
                background: '#164438',
              }}
            >
              <row.icon size={28} color={TEAL} strokeWidth={1.5} />
            </div>
            <div style={{ paddingTop: 7 }}>
              <div style={{ fontSize: 29, fontWeight: 550 }}>{row.title}</div>
              <div
                style={{
                  fontSize: 22,
                  lineHeight: 1.4,
                  marginTop: 12,
                  maxWidth: 630,
                  color: MUTED,
                }}
              >
                {row.sub}
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  )
}

export function InstalledBaseVisual() {
  return (
    <div style={{ padding: '25px 20px' }}>
      <Small>THE SHARED FOUNDATION: INSTALLED MACHINES</Small>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-around',
          alignItems: 'center',
          marginTop: 60,
          marginBottom: 55,
        }}
      >
        {[
          { title: 'Customer', icon: Users },
          { title: 'Machine', icon: Cog },
          { title: 'Dealer', icon: Building2 },
        ].map((node, i) => (
          <Reveal key={node.title} delay={i * 25} style={{ textAlign: 'center' }}>
            <div
              style={{
                width: 100,
                height: 100,
                display: 'grid',
                placeItems: 'center',
                background: '#164438',
                borderRadius: 24,
                marginBottom: 20,
              }}
            >
              <node.icon size={40} color={TEAL} strokeWidth={1.5} />
            </div>
            <div style={{ fontSize: 25 }}>{node.title}</div>
          </Reveal>
        ))}
      </div>
      {[
        'Ownership & dealer responsibility',
        'Stock, parts orders & returns',
        'Repair history & warranty claims',
      ].map((row, i) => (
        <Reveal
          key={row}
          delay={85 + i * 30}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 18,
            borderTop: border,
            paddingBlock: 23,
            fontSize: 25,
          }}
        >
          <Database size={26} color={TEAL} /> {row}
        </Reveal>
      ))}
      <Reveal delay={180} style={{ color: MUTED, fontSize: 21, marginTop: 20 }}>
        Validate → exchange → keep records current
      </Reveal>
    </div>
  )
}

export function CategoriesVisual() {
  const icons = [
    Package,
    CircleDot,
    SlidersHorizontal,
    Snowflake,
    Cog,
    Zap,
    Filter,
    Droplets,
    Droplets,
    Layers,
  ]
  const categories = story.examples.categories.map((name, i) => ({
    name,
    icon: icons[i] ?? Package,
  }))
  return (
    <div style={{ padding: '25px 20px' }}>
      <Small>CATEGORIES IN THE CURRENT CATALOGUE</Small>
      <div
        style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 35px', marginTop: 35 }}
      >
        {categories.map((category, i) => (
          <Reveal
            key={category.name}
            delay={i * 12}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 22,
              paddingBlock: 26,
              borderBottom: border,
              fontSize: 26,
            }}
          >
            <category.icon size={32} color={TEAL} strokeWidth={1.5} />
            {category.name}
          </Reveal>
        ))}
      </div>
      <Reveal delay={145} style={{ color: MUTED, marginTop: 35, fontSize: 23 }}>
        Narrow by machine, category and search term.
      </Reveal>
    </div>
  )
}

export function PortalDetailVisual() {
  return (
    <div style={{ background: PAPER, color: INK, borderRadius: 24, padding: '32px 40px' }}>
      <Small light>PART INFORMATION AT A GLANCE</Small>
      <div style={{ display: 'flex', gap: 28, alignItems: 'center', marginBlock: 25 }}>
        <Img
          src={bucket}
          style={{ width: 240, height: 170, objectFit: 'contain', mixBlendMode: 'multiply' }}
        />
        <div>
          <div style={{ color: '#00756a', fontSize: 20 }}>{story.examples.part.number}</div>
          <div
            style={{
              fontSize: 31,
              lineHeight: 1.2,
              fontWeight: 600,
              marginTop: 12,
              whiteSpace: 'pre-line',
            }}
          >
            {story.examples.part.label}
          </div>
        </div>
      </div>
      {[
        ['Category', story.examples.part.category],
        ['Machine fitment', 'Recorded compatible models'],
        ['Price & availability', 'Shown when recorded'],
        ['Supply & source', 'Evidence and data labels'],
      ].map(([label, value], i) => (
        <Reveal
          key={label}
          delay={25 + i * 28}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: 15,
            paddingBlock: 23,
            borderTop: '1px solid #cfd9cf',
            fontSize: 23,
          }}
        >
          <span style={{ fontWeight: 600 }}>{label}</span>
          <span style={{ color: '#56685e' }}>{value}</span>
        </Reveal>
      ))}
    </div>
  )
}
