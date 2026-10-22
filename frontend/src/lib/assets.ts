/**
 * Asset resolution. Files placed in frontend/src/assets are discovered at build time, so there is never a
 * failed request for a missing image: no file means the placeholder renders instead.
 *
 *   frontend/src/assets/machines/<slug>/main.webp   (also detail.webp)
 *   frontend/src/assets/parts/<part-number>/main.jpg   (any of webp, avif, jpg, png)
 *   frontend/src/assets/plants/<plantId>.webp
 *   frontend/src/assets/editorial/<name>.webp   (machinery-at-work, mechanical-detail, engineering, work-environment, service)
 *   frontend/src/assets/videos/<filmId>.mp4            (desktop, 1080p)
 *   frontend/src/assets/videos/<filmId>-mobile.mp4     (phones and Save-Data, 540p)
 *   frontend/src/assets/videos/<filmId>-poster.webp    (shown before play, and instead of video for reduced motion)
 */
const machineFiles = import.meta.glob<string>('../assets/machines/*/*.{webp,avif,jpg,jpeg,png}', {
  eager: true,
  query: '?url',
  import: 'default',
})
const plantFiles = import.meta.glob<string>('../assets/plants/*.{webp,avif,jpg,jpeg,png}', {
  eager: true,
  query: '?url',
  import: 'default',
})
const editorialFiles = import.meta.glob<string>('../assets/editorial/*.{webp,avif,jpg,jpeg,png}', {
  eager: true,
  query: '?url',
  import: 'default',
})
const partFiles = import.meta.glob<string>('../assets/parts/*/*.{webp,avif,jpg,jpeg,png}', {
  eager: true,
  query: '?url',
  import: 'default',
})
const videoFiles = import.meta.glob<string>('../assets/videos/*.{mp4,webm}', {
  eager: true,
  query: '?url',
  import: 'default',
})
const posterFiles = import.meta.glob<string>('../assets/videos/*-poster.{webp,jpg,jpeg,png}', {
  eager: true,
  query: '?url',
  import: 'default',
})

const byName = (
  files: Record<string, string>,
  folderPattern: RegExp,
  name: string,
): string | undefined => {
  const hit = Object.keys(files).find(
    (path) => folderPattern.test(path) && new RegExp(`/${name}\\.[a-z0-9]+$`).test(path),
  )
  return hit ? files[hit] : undefined
}

export type MachineImageKind = 'main' | 'detail'

export const machineImageUrl = (
  slug: string,
  kind: MachineImageKind = 'main',
): string | undefined => byName(machineFiles, new RegExp(`/machines/${slug}/`), kind)

/**
 * The single place a part image is resolved. Folder = the part's unified part number, lower-case:
 * frontend/src/assets/parts/<part-number>/main.<ext>. Adding a photo there is the whole change; no component knows about files.
 */
export const partImageUrl = (partNumber: string): string | undefined => {
  const slug = partNumber.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  return byName(partFiles, new RegExp(`/parts/${slug}/`), 'main')
}
export const plantImageUrl = (plantId: string): string | undefined =>
  byName(plantFiles, /\/plants\//, plantId)
export const editorialImageUrl = (name: string): string | undefined =>
  byName(editorialFiles, /\/editorial\//, name)
export const videoUrl = (
  filmId: string,
  variant: 'desktop' | 'mobile' = 'desktop',
): string | undefined =>
  byName(videoFiles, /\/videos\//, variant === 'mobile' ? `${filmId}-mobile` : filmId)
export const filmPosterUrl = (filmId: string): string | undefined =>
  byName(posterFiles, /\/videos\//, `${filmId}-poster`)

/** Where a machine image should be placed to replace its placeholder. */
export const machineAssetPath = (slug: string, kind: MachineImageKind = 'main'): string =>
  `frontend/src/assets/machines/${slug}/${kind}.webp`
