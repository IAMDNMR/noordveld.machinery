import { Boxes, Building2, Factory, Tractor, Truck, type LucideIcon } from 'lucide-react'

export const company = {
  name: 'Noordveld Machinery B.V.',
  disclaimer: 'Fictional company and demonstration data.',
  email: 'contact@noordveld.example',
  serviceEmail: 'service@noordveld.example',
} as const

export interface NavItem {
  label: string
  to: string
  /** Leaves the single-page app (a separate page of the same site), so it needs a normal page load */
  external?: boolean
  /** Small badge shown beside the label */
  tag?: string
}

/** Spark: the introduction and films. The conversation itself lives at SPARK_CHAT_ROUTE. */
export const AGENTIC_ROUTE = '/spark'
export const SPARK_CHAT_ROUTE = '/spark/chat'

export const nav: readonly NavItem[] = [
  { label: 'Machines', to: '/machines' },
  { label: 'Company', to: '/#company' },
  { label: 'Aftersales', to: '/parts-services' },
  { label: 'Parts Portal', to: '/parts-store' },
  { label: 'Ask Spark', to: AGENTIC_ROUTE },
  { label: 'Contact', to: `mailto:${company.email}`, external: true },
]

/** The header shows Aftersales, Parts Portal and Ask Spark; Machines and Company stay reachable from the home page and the footer. */
export const primaryNav: readonly NavItem[] = nav.filter(
  (item) => !['Contact', 'Machines', 'Company'].includes(item.label),
)

/** What each signed-in role works with. Hiding a link is presentation only: the backend checks every request. */
export const navFor = (role: 'END_USER' | 'ORDER_PROCESSOR' | null): readonly NavItem[] =>
  role === 'END_USER'
    ? [
        { label: 'Aftersales', to: '/parts-services' },
        { label: 'Parts Portal', to: '/parts-store' },
        { label: 'Ask Spark', to: AGENTIC_ROUTE },
        { label: 'My Orders', to: '/orders' },
      ]
    : role === 'ORDER_PROCESSOR'
      ? [
          { label: 'Orders', to: '/orders' },
          { label: 'Ask Spark', to: AGENTIC_ROUTE },
          { label: 'Parts Portal', to: '/parts-store' },
          { label: 'Commerce Assistant', to: '/commerce' },
          { label: 'Fulfilment', to: '/orders?queue=needs_fulfilment' },
          { label: 'Shipments', to: '/orders?queue=shipped' },
        ]
      : primaryNav

export interface Industry {
  name: string
  text: string
  icon: LucideIcon
}

/** Broad categories only, each supported by the machine types in the catalog. */
export const industries: readonly Industry[] = [
  {
    name: 'Material handling',
    text: 'Pallet trucks, forklifts, reach trucks, stackers and telehandlers.',
    icon: Boxes,
  },
  {
    name: 'Industrial operations',
    text: 'Conveyor modules, transfer carts and pallet elevators for moving goods through a site.',
    icon: Factory,
  },
  {
    name: 'Logistics',
    text: 'Equipment for loading, stacking and transferring pallets.',
    icon: Truck,
  },
  {
    name: 'Construction and site operations',
    text: 'Wheel loaders, skid steer loaders and articulated loaders.',
    icon: Building2,
  },
  {
    name: 'Agricultural and general equipment',
    text: 'Loaders and telehandlers with attachments such as bale spikes and grapples.',
    icon: Tractor,
  },
]

export type FilmId = 'hero' | 'brand' | 'machinery' | 'engineering' | 'service' | 'machine'

export interface Film {
  id: FilmId
  title: string
  /** Intended content of the final film */
  brief: string
  ratio: '16 / 9'
  /** Large ghost word shown behind the film */
  word: string
}

/** Film slots. Drop a rendered file at src/assets/videos/<id>.mp4 and it replaces the placeholder. */
export const films: Record<FilmId, Film> = {
  hero: {
    id: 'hero',
    title: 'Noordveld at work',
    brief: 'Machines operating, manufacturing, mechanical close-ups, European industrial settings.',
    ratio: '16 / 9',
    word: 'Noordveld',
  },
  brand: {
    id: 'brand',
    title: 'Brand film',
    brief: 'The company, its machinery and its engineering.',
    ratio: '16 / 9',
    word: 'Noordveld',
  },
  machinery: {
    id: 'machinery',
    title: 'Machinery film',
    brief: 'Machinery operating in real work environments.',
    ratio: '16 / 9',
    word: 'At work',
  },
  engineering: {
    id: 'engineering',
    title: 'Engineering film',
    brief: 'Manufacturing, engineering, mechanical detail and testing.',
    ratio: '16 / 9',
    word: 'Engineered',
  },
  service: {
    id: 'service',
    title: 'Service film',
    brief: 'A technician servicing a machine on site.',
    ratio: '16 / 9',
    word: 'Service',
  },
  machine: {
    id: 'machine',
    title: 'Machine film',
    brief: 'This machine at work.',
    ratio: '16 / 9',
    word: 'At work',
  },
}
