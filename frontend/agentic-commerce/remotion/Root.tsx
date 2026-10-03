import { Composition, useCurrentFrame, useVideoConfig } from 'remotion'
import '@fontsource-variable/inter'
import '../src/styles/tokens.css'
import { EvolutionFilm } from '../src/film/EvolutionFilm'
import { FILM_FPS, FILM_FRAMES, FORMATS, type FilmFormat } from '../src/film/timeline'

/** Frame-driven wrapper: Remotion supplies the frame, the composition stays a pure function of time. */
function Film({ format }: { format: FilmFormat }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  return <EvolutionFilm time={frame / fps} format={format} />
}

const FilmLandscape = () => <Film format="landscape" />
const FilmSquare = () => <Film format="square" />
const FilmVertical = () => <Film format="vertical" />

export function RemotionRoot() {
  return (
    <>
      <Composition id="EvolutionFilm" component={FilmLandscape} durationInFrames={FILM_FRAMES} fps={FILM_FPS} {...FORMATS.landscape} />
      <Composition id="EvolutionFilmSquare" component={FilmSquare} durationInFrames={FILM_FRAMES} fps={FILM_FPS} {...FORMATS.square} />
      <Composition id="EvolutionFilmVertical" component={FilmVertical} durationInFrames={FILM_FRAMES} fps={FILM_FPS} {...FORMATS.vertical} />
    </>
  )
}
