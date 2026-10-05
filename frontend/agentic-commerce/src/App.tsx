import { Footer, Nav } from './components/Chrome'
import { Agentic } from './components/sections/Agentic'
import { AgenticIntro } from './components/sections/AgenticIntro'
import { Closing } from './components/sections/Closing'
import { EvolutionVideoSlot } from './components/sections/EvolutionVideoSlot'
import { LaunchFilm } from './components/launch/LaunchFilm'

export default function App() {
  return (
    <>
      <a className="skip-link" href="#agentic">
        Skip to the content
      </a>
      <Nav />
      <main>
        <EvolutionVideoSlot />
        <AgenticIntro />
        <LaunchFilm />
        <Agentic />
        <Closing />
      </main>
      <Footer />
    </>
  )
}
