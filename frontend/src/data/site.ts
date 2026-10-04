import { useEffect, useState } from 'react'
import { ApiError } from '../api'
import { getSiteOverview, type SiteOverview } from '../api/site'
import type { Machine, Plant, SiteData } from '../types/catalog'

/**
 * Website facts, loaded once from the backend and shared by every section. The frontend keeps no catalogue of its own:
 * machines, plants, brands and part counts all come from the Noordveld graph through /api/v1/site/overview.
 */
const plantKey = (city: string | null | undefined): string => (city ?? '').toLowerCase()

export function adapt(o: SiteOverview): SiteData {
  const machines: Machine[] = o.machines.map((m) => {
    const brand = m.brand ?? 'Noordveld'
    const city = m.plant_city ?? m.plant ?? ''
    const range = brand === 'Noordveld' ? 'the Noordveld range' : `the ${brand} range`
    const relatedParts = m.parts.map((p) => ({ partNo: p.part_number, name: p.name, category: p.category ?? 'Uncategorised', specNote: p.spec_note ?? '' }))
    return {
      model: m.model,
      slug: m.slug,
      name: m.name,
      family: m.family ?? 'Other',
      brand,
      acquired: m.acquired ?? undefined,
      plantId: plantKey(m.plant_city),
      plant: m.plant ?? 'Not recorded',
      description: `${m.model} is a ${m.name} from ${range}, built at the ${city} plant.${m.acquired ? ` ${brand} joined Noordveld in ${m.acquired}.` : ''}`,
      specifications: {
        Model: m.model,
        'Machine type': m.name,
        Family: m.family ?? 'Not recorded',
        Plant: m.plant ?? 'Not recorded',
        Brand: m.acquired ? `${brand} (acquired ${m.acquired})` : brand,
        'Parts in catalogue': String(relatedParts.length),
      },
      relatedParts,
      attachments: m.attachments,
      application: m.profile?.application ? { text: m.profile.application, context: m.profile.operating_context, introduced: m.profile.introduction_year } : null,
    }
  })
  const plants: Plant[] = o.plants.map((p) => ({
    id: plantKey(p.city),
    city: p.city,
    country: p.country ?? p.country_code ?? '',
    countryCode: p.country_code ?? '',
    brand: p.brand ?? 'Noordveld',
    acquired: p.acquired_year ?? undefined,
    machineCount: p.machine_count,
    lat: p.lat,
    lon: p.lon,
  }))
  const featured = machines.reduce<Machine | null>((best, m) => (!best || m.relatedParts.length > best.relatedParts.length ? m : best), null)
  return { machines, plants, families: o.families, featured, partCount: o.part_count, partCategories: o.part_categories }
}

let pending: Promise<SiteData> | null = null
let loaded: SiteData | null = null

export function loadSite(): Promise<SiteData> {
  pending ??= getSiteOverview()
    .then((o) => (loaded = adapt(o)))
    .catch((e: unknown) => {
      pending = null // a later visit may try again
      throw e
    })
  return pending
}

export function useSite(): { data: SiteData | null; error: ApiError | null } {
  const [data, setData] = useState<SiteData | null>(loaded)
  const [error, setError] = useState<ApiError | null>(null)
  useEffect(() => {
    if (loaded) return
    let live = true
    loadSite().then(
      (d) => live && setData(d),
      (e: unknown) => live && setError(e instanceof ApiError ? e : new ApiError(0, 'unknown', 'The site data could not be loaded.')),
    )
    return () => {
      live = false
    }
  }, [])
  return { data, error }
}

export const machinesAt = (site: SiteData, plantId: string): readonly Machine[] => site.machines.filter((m) => m.plantId === plantId)

/** "Netherlands" -> "the Netherlands" in running text (a language rule, not data) */
export const inText = (country: string): string => (/^(Netherlands|United )/.test(country) ? `the ${country}` : country)

export const capitalise = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1)

/** "three", "two": counts written out for headings */
export const countWord = (n: number): string => ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'][n] ?? String(n)
