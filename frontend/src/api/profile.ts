import { apiDelete, apiGet, apiPut } from './client'

export type Profile = {
  machines: string[]
  preferred_machine: string | null
  country: string | null
  ship_to_id: string | null
  dealer_id: string | null
  name: string | null
  company: string | null
  email: string | null
  phone: string | null
  receiver_name: string | null
  receiver_phone: string | null
  delivery_preference: 'fastest' | 'cheapest' | null
  delivery_notes: string | null
}
export type ProfileState = {
  stored: boolean
  consent_at: string | null
  profile: Profile | null
  account: { name: string; email: string; company: string | null }
}

export const getProfile = (signal?: AbortSignal) => apiGet<ProfileState>('/me/profile', {}, signal)

/** Stores the profile only with consent === true; false erases it on the server. */
export const saveProfile = (profile: Partial<Profile>, consent: boolean) =>
  apiPut<ProfileState>('/me/profile', { consent, ...profile })
export const eraseProfile = () => apiDelete<ProfileState>('/me/profile')
