/** Labels for the catalogue's part statuses (PartCatalogProfile.part_status), shared by the Parts Store and Parts Intelligence. */
export type PartStatusCode = 'VERIFIED' | 'IDENTIFICATION_REQUIRED' | 'AMBIGUOUS' | 'UNVERIFIED'

export const STATUS_LABEL: Record<PartStatusCode, string> = {
  VERIFIED: 'Verified',
  IDENTIFICATION_REQUIRED: 'Identification required',
  AMBIGUOUS: 'Ambiguous',
  UNVERIFIED: 'Unverified',
}

const isStatus = (value: string | null | undefined): value is PartStatusCode => !!value && value in STATUS_LABEL

/** Any status the catalogue does not define reads as Unverified; a raw code is never shown. */
export const statusLabel = (code: string | null | undefined): string => (isStatus(code) ? STATUS_LABEL[code] : STATUS_LABEL.UNVERIFIED)

/** `MACHINE_VARIANT_OR_SERIAL_RANGE` → "Machine variant or serial range". Codes that are statuses use the status label. */
export const codeLabel = (code: string | null | undefined): string | null => {
  if (!code) return null
  if (isStatus(code)) return STATUS_LABEL[code]
  const text = code.replace(/_/g, ' ').toLowerCase()
  return text.charAt(0).toUpperCase() + text.slice(1)
}
