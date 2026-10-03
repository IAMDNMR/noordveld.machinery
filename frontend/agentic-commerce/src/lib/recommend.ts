/**
 * Deterministic demonstration of "requirement + constraints + priority → recommendation".
 * Everything here is sample data and simple arithmetic. It is not connected to inventory, suppliers,
 * payments or a model, and the interfaces are shaped so a real source can replace it later.
 */

export type Priority = 'best-match' | 'lowest-price' | 'fastest-delivery' | 'closest-availability'

export interface Requirement {
  budget: number
  /** Whole days within which the outcome is needed. */
  maxDeliveryDays: number
  /** Distance at which availability still counts as a suitable location. */
  maxDistanceKm: number
}

export interface CommerceRecommendation {
  id: string
  price: number
  availability: string
  distance?: number
  deliveryTime: string
  compatibility: boolean
  reason: string
  deliveryDays: number
}

export interface Checks {
  budget: boolean
  compatible: boolean
  timeframe: boolean
  location: boolean
}

export interface Evaluation {
  recommended: CommerceRecommendation
  checks: Record<string, Checks>
  eligible: ReadonlySet<string>
  /** User-facing sentence explaining the recommendation for the selected priority. */
  explanation: string
}

export const priorities: readonly { id: Priority; label: string }[] = [
  { id: 'best-match', label: 'Best Match' },
  { id: 'lowest-price', label: 'Lowest Price' },
  { id: 'fastest-delivery', label: 'Fastest Delivery' },
  { id: 'closest-availability', label: 'Closest Availability' },
]

const distanceOf = (o: CommerceRecommendation): number => o.distance ?? Number.POSITIVE_INFINITY
const money = (n: number): string => `€${n.toLocaleString('en-IE')}`

const normalised = (value: number, all: readonly number[]): number => {
  const min = Math.min(...all)
  const max = Math.max(...all)
  return max === min ? 0 : (value - min) / (max - min)
}

export function evaluate(requirement: Requirement, options: readonly CommerceRecommendation[], priority: Priority): Evaluation {
  const checks: Record<string, Checks> = {}
  for (const o of options) {
    checks[o.id] = {
      budget: o.price <= requirement.budget,
      compatible: o.compatibility,
      timeframe: o.deliveryDays <= requirement.maxDeliveryDays,
      location: distanceOf(o) <= requirement.maxDistanceKm,
    }
  }
  // Hard constraints come first: a stated requirement is never traded away for a priority.
  const pool = options.filter((o) => checks[o.id].budget && checks[o.id].compatible && checks[o.id].timeframe)
  const candidates = pool.length > 0 ? pool : options
  const eligible = new Set(pool.map((o) => o.id))

  const score = (o: CommerceRecommendation): number => {
    const price = normalised(o.price, candidates.map((c) => c.price))
    const days = normalised(o.deliveryDays, candidates.map((c) => c.deliveryDays))
    const dist = normalised(distanceOf(o), candidates.map(distanceOf))
    switch (priority) {
      case 'lowest-price':
        return price
      case 'fastest-delivery':
        return days
      case 'closest-availability':
        return dist
      default:
        return price + days + dist
    }
  }
  const recommended = [...candidates].sort((a, b) => score(a) - score(b) || a.price - b.price)[0]

  const cheaperExcluded = options.find((o) => !eligible.has(o.id) && o.price < recommended.price)
  const fasterExcluded = options.find((o) => !eligible.has(o.id) && o.deliveryDays < recommended.deliveryDays)
  const label = `Option ${recommended.id}`
  const explanations: Record<Priority, string> = {
    'best-match': `${label} is the best match for the stated budget and required delivery timeline.`,
    'lowest-price': `${label} has the lowest price (${money(recommended.price)}) among the options that meet your requirement.${cheaperExcluded ? ` Option ${cheaperExcluded.id} costs less, but ${cheaperExcluded.availability.toLowerCase()}, which is outside what you asked for.` : ''}`,
    'fastest-delivery': `${label} is the fastest option that fits: ${recommended.availability.toLowerCase()}.${fasterExcluded ? ` Nothing faster meets your other requirements.` : ''}`,
    'closest-availability': `${label} is available closest to you, ${recommended.distance} km away, while still meeting your budget and timeline.`,
  }
  return { recommended, checks, eligible, explanation: explanations[priority] }
}

/** The single requirement used throughout the demonstration. */
export const demoRequirement: Requirement = { budget: 80_000, maxDeliveryDays: 2, maxDistanceKm: 150 }

export const demoOptions: readonly CommerceRecommendation[] = [
  { id: 'A', price: 72_000, availability: 'Available tomorrow', distance: 120, deliveryTime: 'Tomorrow', deliveryDays: 1, compatibility: true, reason: 'Within budget, compatible, and arrives with a day to spare.' },
  { id: 'B', price: 78_000, availability: 'Available in two days', distance: 60, deliveryTime: 'In two days', deliveryDays: 2, compatibility: true, reason: 'Within budget and compatible, arriving right at the deadline from the closest location.' },
  { id: 'C', price: 65_000, availability: 'Available in five days', distance: 300, deliveryTime: 'In five days', deliveryDays: 5, compatibility: true, reason: 'The lowest price, but it would not arrive within two days.' },
]

export const formatPrice = money
