import './overview-video-slot.css'

/** On-demand film playback: no autoplay, with optional English captions enabled. */
export function OverviewVideoSlot({
  title,
  film,
}: {
  title: string
  film: 'aftersales' | 'parts-portal'
}) {
  const base = `${import.meta.env.BASE_URL}films/${film}`
  return (
    <div className="overview-video-slot overview-video-slot--ready">
      <video controls playsInline preload="none" poster={`${base}.jpg`} aria-label={title}>
        <source src={`${base}.mp4`} type="video/mp4" />
        <track kind="captions" src={`${base}.vtt`} srcLang="en" label="English" default />
        Your browser cannot play this film. <a href={`${base}.mp4`}>Download the film</a>.
      </video>
    </div>
  )
}
