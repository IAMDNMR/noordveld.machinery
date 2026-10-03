import { Footer, Nav } from './components/Chrome'
import { Agentic } from './components/sections/Agentic'
import { Closing } from './components/sections/Closing'
import { Theory } from './components/theory/Theory'
import { LaunchFilm } from './components/launch/LaunchFilm'
import { CommerceEvolutionHero } from './components/evolution/CommerceEvolutionHero'

export default function App() {
  return (
    <>
      <a className="skip-link" href="#theory">
        Skip to the explanation
      </a>
      <Nav />
      <main>
        <CommerceEvolutionHero />
        <Theory />
        <LaunchFilm />
        <Agentic />
        <Closing />
      </main>
      <Footer />
    </>
  )
}
