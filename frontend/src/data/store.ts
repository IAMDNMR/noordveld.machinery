import { Anvil, Cog, Disc3, Droplet, Droplets, Fan, Filter, Joystick, Shovel, Zap, type LucideIcon } from 'lucide-react'
import type { Availability, PartStatus, StorePartRaw } from '../types/store'
import { storeCategories, storeCompliance, storeCountries, storeParts, storeShippingRates, storeWarehouses } from './store.generated'

export { storeCategories, storeCompliance, storeCountries, storeShippingRates, storeWarehouses }

export const STORE_ROUTE = '/parts-store'
export const STORE_DISCLAIMER = 'Demonstration store. Prices, stock, delivery and compliance are synthetic demo data; fitment comes from the Noordveld catalogue.'

export interface StorePart extends StorePartRaw {
  /** URL segment, the part number in lower case */
  slug: string
}

export const allParts: readonly StorePart[] = storeParts.map((p) => ({ ...p, slug: p.no.toLowerCase() }))
const byId = new Map(allParts.map((p) => [p.id, p]))
const bySlug = new Map(allParts.map((p) => [p.slug, p]))
export const partById = (id: string): StorePart | undefined => byId.get(id)
export const partBySlug = (slug: string): StorePart | undefined => bySlug.get(slug.toLowerCase())
export const partPath = (p: StorePart): string => `${STORE_ROUTE}/${p.slug}`

export const categoryIcon: Record<string, LucideIcon> = {
  Hydraulics: Droplets,
  Drivetrain: Cog,
  Electrical: Zap,
  Structural: Anvil,
  Filtration: Filter,
  Brakes: Disc3,
  Cooling: Fan,
  'Cab & Controls': Joystick,
  Attachments: Shovel,
  Lubrication: Droplet,
}
export const iconFor = (category: string): LucideIcon => categoryIcon[category] ?? Cog

/* ───────── Formatting ───────── */
const euro = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'EUR' })
export const eur = (n: number): string => euro.format(n)

/* ───────── Availability and status ───────── */
export const availabilityMeta: Record<Availability, { label: string; tone: 'ok' | 'warn' | 'late'; rank: number }> = {
  IN_STOCK: { label: 'In stock', tone: 'ok', rank: 0 },
  LIMITED: { label: 'Limited stock', tone: 'warn', rank: 1 },
  BACKORDER: { label: 'Backorder', tone: 'late', rank: 2 },
}

export const statusMeta: Record<PartStatus, { label: string; short: string }> = {
  VERIFIED: { label: 'Fitment verified', short: 'Verified' },
  UNVERIFIED: { label: 'Fitment not yet verified', short: 'Unverified' },
  IDENTIFICATION_REQUIRED: { label: 'Machine variant needed', short: 'Identify variant' },
  AMBIGUOUS: { label: 'Confirm before ordering', short: 'Confirm first' },
}

export const totalStock = (p: StorePart): number => Object.values(p.stock).reduce((a, b) => a + b, 0)

/** One-line stock statement for cards and the detail page. */
export const stockLine = (p: StorePart): string => {
  if (p.availability === 'BACKORDER') return p.backorder ? `Restock in about ${p.backorder.days} days` : 'On backorder'
  const total = totalStock(p)
  const sites = Object.values(p.stock).filter((n) => n > 0).length
  return `${total} available at ${sites} ${sites === 1 ? 'warehouse' : 'warehouses'}`
}

/* ───────── Delivery (demo rates) ───────── */
export type ShipMethod = 'STANDARD' | 'EXPRESS'
const bandOrder = ['LOCAL', 'REGIONAL', 'NATIONAL', 'LONG_DISTANCE']

export const bandLabel: Record<string, string> = {
  LOCAL: 'Local, up to 100 km',
  REGIONAL: 'Regional, 100–250 km',
  NATIONAL: 'National, 250–500 km',
  LONG_DISTANCE: 'Long distance, 500 km and more',
}

export const ratesByBand = bandOrder.map((band) => ({
  band,
  standard: storeShippingRates.find((r) => r.band === band && r.method === 'STANDARD'),
  express: storeShippingRates.find((r) => r.band === band && r.method === 'EXPRESS'),
}))

/** Cart shipping is an estimate at the regional demo rate. */
export const regionalRate = (method: ShipMethod) => storeShippingRates.find((r) => r.band === 'REGIONAL' && r.method === method)

export const cheapestStandard = Math.min(...storeShippingRates.filter((r) => r.method === 'STANDARD').map((r) => r.price))

/* ───────── Search ───────── */
const norm = (s: string): string => s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

const index = new Map(
  allParts.map((p) => {
    const text = norm([p.no, p.no.replace(/-/g, ''), p.legacyNo, p.name, p.category, p.subcategory, p.specNote, p.fits.join(' '), p.aliases.join(' '), p.legacyBusiness].join(' '))
    return [p.id, { text, name: norm(p.name), no: norm(p.no) }]
  }),
)

/** Score 0 means no match. Every word in the query has to be found; part numbers and name starts rank first. */
export const searchScore = (p: StorePart, query: string): number => {
  const tokens = norm(query).split(' ').filter(Boolean)
  if (!tokens.length) return 1
  const entry = index.get(p.id)
  if (!entry) return 0
  let score = 0
  for (const t of tokens) {
    if (!entry.text.includes(t)) return 0
    score += 1
    if (entry.name.startsWith(t)) score += 3
    else if (entry.name.includes(t)) score += 2
    if (entry.no.startsWith(t)) score += 4
  }
  if (entry.no === norm(query)) score += 20
  return score
}

export const searchParts = (query: string, limit = 6): StorePart[] =>
  allParts
    .map((p) => ({ p, s: searchScore(p, query) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, limit)
    .map((x) => x.p)

/* ───────── Machines the catalogue says a part fits ───────── */
export const fitModels: readonly string[] = Array.from(new Set(allParts.flatMap((p) => p.fits))).sort((a, b) => a.localeCompare(b, 'en', { numeric: true }))

export const priceBounds = {
  min: Math.floor(Math.min(...allParts.map((p) => p.price))),
  max: Math.ceil(Math.max(...allParts.map((p) => p.price))),
}
