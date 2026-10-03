/**
 * Asset resolution. Files placed in src/assets are discovered at build time, so there is never a
 * failed request for a missing image: no file means the placeholder renders instead.
 *
 *   src/assets/machines/<slug>/main.webp   (also detail.webp)
 *   src/assets/plants/<plantId>.webp
 *   src/assets/editorial/<name>.webp   (machinery-at-work, mechanical-detail, engineering, work-environment, service)
 *   src/assets/videos/<filmId>.mp4            (desktop, 1080p)
 *   src/assets/videos/<filmId>-mobile.mp4     (phones and Save-Data, 540p)
 *   src/assets/videos/<filmId>-poster.webp    (shown before play, and instead of video for reduced motion)
 */
const machineFiles = import.meta.glob<string>('../assets/machines/*/*.{webp,avif,jpg,jpeg,png}', { eager: true, query: '?url', import: 'default' })
const plantFiles = import.meta.glob<string>('../assets/plants/*.{webp,avif,jpg,jpeg,png}', { eager: true, query: '?url', import: 'default' })
const editorialFiles = import.meta.glob<string>('../assets/editorial/*.{webp,avif,jpg,jpeg,png}', { eager: true, query: '?url', import: 'default' })
const videoFiles = import.meta.glob<string>('../assets/videos/*.{mp4,webm}', { eager: true, query: '?url', import: 'default' })
const posterFiles = import.meta.glob<string>('../assets/videos/*-poster.{webp,jpg,jpeg,png}', { eager: true, query: '?url', import: 'default' })

const byName = (files: Record<string, string>, folderPattern: RegExp, name: string): string | undefined => {
  const hit = Object.keys(files).find((path) => folderPattern.test(path) && new RegExp(`/${name}\\.[a-z0-9]+$`).test(path))
  return hit ? files[hit] : undefined
}

export type MachineImageKind = 'main' | 'detail'

export const machineImageUrl = (slug: string, kind: MachineImageKind = 'main'): string | undefined => byName(machineFiles, new RegExp(`/machines/${slug}/`), kind)
export const plantImageUrl = (plantId: string): string | undefined => byName(plantFiles, /\/plants\//, plantId)
export const editorialImageUrl = (name: string): string | undefined => byName(editorialFiles, /\/editorial\//, name)
export const videoUrl = (filmId: string, variant: 'desktop' | 'mobile' = 'desktop'): string | undefined =>
  byName(videoFiles, /\/videos\//, variant === 'mobile' ? `${filmId}-mobile` : filmId)
export const filmPosterUrl = (filmId: string): string | undefined => byName(posterFiles, /\/videos\//, `${filmId}-poster`)

/** Where a machine image should be placed to replace its placeholder. */
export const machineAssetPath = (slug: string, kind: MachineImageKind = 'main'): string => `src/assets/machines/${slug}/${kind}.webp`
