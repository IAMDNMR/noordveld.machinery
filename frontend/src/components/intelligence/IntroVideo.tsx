import { Play, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

/** A link that opens the Parts Intelligence introduction film in a player overlay. Nothing plays until it is asked for. */
export function IntroVideo() {
  const [open, setOpen] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const video = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const d = dialog.current
    if (!d) return
    if (open) {
      if (!d.open) d.showModal?.()
      video.current?.play().catch(() => {
        /* playback refused: the controls stay */
      })
    } else {
      video.current?.pause()
      if (d.open) d.close?.()
    }
  }, [open])

  return (
    <>
      <button type="button" className="pih-play" onClick={() => setOpen(true)}>
        <span className="pih-play__icon" aria-hidden="true">
          <Play size={13} strokeWidth={2.4} fill="currentColor" />
        </span>
        Watch the introduction
      </button>
      <dialog ref={dialog} className="pih-film" aria-label="Parts Intelligence introduction" onClose={() => setOpen(false)}>
        <div className="pih-film__frame">
          <button type="button" className="pih-film__close" onClick={() => setOpen(false)} aria-label="Close the introduction">
            <X size={20} strokeWidth={2} aria-hidden="true" />
          </button>
          {/* the introduction film has no caption file yet; its narration is summarised on the page itself */}
          {/* oxlint-disable-next-line jsx-a11y/media-has-caption */}
          <video ref={video} src="/parts-intelligence-intro.mp4" poster="/parts-intelligence-intro.jpg" controls playsInline preload="none">
            Your browser cannot play this video.
          </video>
        </div>
      </dialog>
    </>
  )
}
