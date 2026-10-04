import { apiGet } from './client'

/** Website facts from the backend (backend/app/services/site.py), read from the Noordveld graph. */
export interface SitePart {
  part_number: string
  name: string
  category: string | null
  spec_note: string | null
  data_status: string | null
}

export interface SiteMachine {
  model: string
  slug: string
  machine_id: string
  /** Machine type */
  name: string
  full_name: string
  family: string | null
  brand: string | null
  acquired: number | null
  plant_id: string | null
  plant: string | null
  plant_city: string | null
  plant_country_code: string | null
  data_status: string | null
  parts: SitePart[]
  attachments: string[]
  /** Synthetic demo profile (application, lifecycle, introduction year); labelled as demo data in the UI */
  profile: { application: string | null; operating_context: string | null; lifecycle_status: string | null; introduction_year: number | null; data_status: string | null } | null
}

export interface SitePlant {
  plant_id: string
  name: string
  city: string
  country_code: string | null
  country: string | null
  brand: string | null
  acquired_year: number | null
  machine_count: number
  data_status: string | null
  /** City-centre coordinates for drawing the map; null when the city is not in the map reference */
  lat: number | null
  lon: number | null
}

export interface SiteOverview {
  machines: SiteMachine[]
  plants: SitePlant[]
  families: string[]
  part_count: number
  part_categories: { name: string; count: number }[]
}

export const getSiteOverview = (signal?: AbortSignal): Promise<SiteOverview> => apiGet<SiteOverview>('/site/overview', {}, signal)
