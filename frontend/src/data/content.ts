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

/** The Agentic E-Commerce introduction page, built into this project and served from the same site. */
export const AGENTIC_ROUTE = '/agentic-commerce/'

export const nav: readonly NavItem[] = [
  { label: 'Agentic E-Commerce', to: AGENTIC_ROUTE, external: true },
  { label: 'Parts Store', to: '/parts-store', tag: 'Agentic' },
]

export interface Industry {
  name: string
  text: string
  icon: LucideIcon
}

/** Broad categories only, each supported by the machine types in the catalog. */
export const industries: readonly Industry[] = [
  { name: 'Material handling', text: 'Pallet trucks, forklifts, reach trucks, stackers and telehandlers.', icon: Boxes },
  { name: 'Industrial operations', text: 'Conveyor modules, transfer carts and pallet elevators for moving goods through a site.', icon: Factory },
  { name: 'Logistics', text: 'Equipment for loading, stacking and transferring pallets.', icon: Truck },
  { name: 'Construction and site operations', text: 'Wheel loaders, skid steer loaders and articulated loaders.', icon: Building2 },
  { name: 'Agricultural and general equipment', text: 'Loaders and telehandlers with attachments such as bale spikes and grapples.', icon: Tractor },
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
  hero: { id: 'hero', title: 'Noordveld at work', brief: 'Machines operating, manufacturing, mechanical close-ups, European industrial settings.', ratio: '16 / 9', word: 'Noordveld' },
  brand: { id: 'brand', title: 'Brand film', brief: 'The company, its machinery and its engineering.', ratio: '16 / 9', word: 'Noordveld' },
  machinery: { id: 'machinery', title: 'Machinery film', brief: 'Machinery operating in real work environments.', ratio: '16 / 9', word: 'At work' },
  engineering: { id: 'engineering', title: 'Engineering film', brief: 'Manufacturing, engineering, mechanical detail and testing.', ratio: '16 / 9', word: 'Engineered' },
  service: { id: 'service', title: 'Service film', brief: 'A technician servicing a machine on site.', ratio: '16 / 9', word: 'Service' },
  machine: { id: 'machine', title: 'Machine film', brief: 'This machine at work.', ratio: '16 / 9', word: 'At work' },
}

