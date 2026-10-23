import { Composition, registerRoot } from 'remotion'
import { CinematicFilm, FILMS } from './CinematicFilms'

function Films() {
  return (
    <>
      <Composition
        id="AftersalesStory"
        component={CinematicFilm}
        defaultProps={{ film: 'aftersales' as const }}
        width={1920}
        height={1080}
        fps={FILMS.aftersales.fps}
        durationInFrames={FILMS.aftersales.frames}
      />
      <Composition
        id="PartsPortalStory"
        component={CinematicFilm}
        defaultProps={{ film: 'parts-portal' as const }}
        width={1920}
        height={1080}
        fps={FILMS['parts-portal'].fps}
        durationInFrames={FILMS['parts-portal'].frames}
      />
    </>
  )
}

registerRoot(Films)
