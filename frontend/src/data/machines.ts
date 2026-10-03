import type { Machine, MachineFamily, Part, Plant, PlantId } from '../types/catalog'
import { catalogMachines, catalogParts } from './catalog.generated'

const plantIdOf = (plant: string): PlantId => {
  if (plant.startsWith('Assen')) return 'assen'
  if (plant.startsWith('Lingen')) return 'lingen'
  return 'coevorden'
}

/** Editorial grouping keyed by model. The catalog provides the machine type; the grouping is ours. */
const familyByModel: Record<string, MachineFamily> = {
  'NV-2100': 'Loading',
  'NV-3200': 'Loading',
  'NV-4500': 'Loading',
  'NV-7500': 'Loading',
  'KFT-600': 'Loading',
  'BTS-250': 'Loading',
  'NV-6000': 'Material handling',
  'KFT-120': 'Material handling',
  'KFT-200': 'Material handling',
  'KFT-450': 'Material handling',
  'KFT-800': 'Material handling',
  'BTS-100': 'Conveying',
  'BTS-500': 'Conveying',
  'BTS-750': 'Conveying',
  'BTS-900': 'Conveying',
}

export const parts: readonly Part[] = catalogParts.map((p) => ({
  partNo: p.partNo,
  name: p.name,
  category: p.category,
  plantId: plantIdOf(p.plantOfOrigin),
  plantOfOrigin: p.plantOfOrigin,
  compatibleModels: p.compatibleModels,
  specNote: p.specNote,
}))

const brandOf = (origin: string): { brand: string; acquired?: number } => {
  const match = /^(.+?) \(acquired (\d{4})\)$/.exec(origin)
  return match ? { brand: match[1], acquired: Number(match[2]) } : { brand: origin }
}

const rangeName = (brand: string): string => (brand === 'Noordveld' ? 'the Noordveld range' : `the ${brand} range`)

export const machines: readonly Machine[] = catalogMachines.map((m) => {
  const { brand, acquired } = brandOf(m.brandOrigin)
  const relatedParts = parts.filter((p) => p.compatibleModels.includes(m.model))
  const plantId = plantIdOf(m.plant)
  const description = `${m.model} is a ${m.machineType} from ${rangeName(brand)}, built at the ${m.plant.replace(/ \(.+\)/, '')} plant.${acquired ? ` ${brand} joined Noordveld in ${acquired}.` : ''}`
  return {
    model: m.model,
    slug: m.model.toLowerCase(),
    name: m.machineType,
    family: familyByModel[m.model],
    brand,
    origin: m.brandOrigin,
    acquired,
    plantId,
    plant: m.plant,
    description,
    specifications: {
      Model: m.model,
      'Machine type': m.machineType,
      Plant: m.plant,
      'Brand / origin': m.brandOrigin,
      'Parts in catalogue': String(relatedParts.length),
    },
    relatedParts,
    attachments: relatedParts.filter((p) => p.category === 'Attachments').map((p) => p.name),
  }
})

export const machineBySlug = (slug: string): Machine | undefined => machines.find((m) => m.slug === slug)

export const families: readonly MachineFamily[] = ['Loading', 'Material handling', 'Conveying']

export const plants: readonly Plant[] = [
  { id: 'assen', city: 'Assen', country: 'Netherlands', countryCode: 'NL', brand: 'Noordveld', lat: 52.99, lon: 6.56 },
  { id: 'lingen', city: 'Lingen', country: 'Germany', countryCode: 'DE', brand: 'Kessler', acquired: 2014, lat: 52.52, lon: 7.32 },
  { id: 'coevorden', city: 'Coevorden', country: 'Netherlands', countryCode: 'NL', brand: 'Bakker', acquired: 2019, lat: 52.66, lon: 6.74 },
]

export const machinesAt = (plantId: PlantId): readonly Machine[] => machines.filter((m) => m.plantId === plantId)

/** Part categories as they appear in the catalog, with the number of catalogued parts in each. */
export const partCategories: readonly { name: string; count: number }[] = Array.from(
  parts.reduce((acc, p) => acc.set(p.category, (acc.get(p.category) ?? 0) + 1), new Map<string, number>()),
)
  .map(([name, count]) => ({ name, count }))
  .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
