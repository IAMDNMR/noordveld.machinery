import { usePageMeta } from '../hooks/usePageMeta'
import { BuiltForWork } from '../sections/BuiltForWork'
import { AgenticTeaser, FinalCta } from '../sections/Closing'
import { Engineering } from '../sections/Engineering'
import { Hero } from '../sections/Hero'
import { Plants } from '../sections/Plants'
import { Portfolio } from '../sections/Portfolio'
import { PartsSection, Service } from '../sections/ServiceParts'
import '../sections/home.css'

export function HomePage() {
  usePageMeta({
    title: 'Noordveld Machinery B.V. — Built for demanding work',
    description: 'Industrial and agricultural machinery engineered for performance, reliability and the work that keeps industries moving. Fictional company and demonstration data.',
    path: '/',
  })
  return (
    <>
      <Hero />
      <Portfolio />
      <BuiltForWork />
      <Engineering />
      <Plants />
      <Service />
      <PartsSection />
      <AgenticTeaser />
      <FinalCta />
    </>
  )
}
