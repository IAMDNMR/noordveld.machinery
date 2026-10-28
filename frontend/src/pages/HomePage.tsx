import { usePageMeta } from '../hooks/usePageMeta'
import { BuiltForWork } from '../sections/BuiltForWork'
import { FinalCta } from '../sections/Closing'
import { CompanyIntroduction } from '../sections/CompanyIntroduction'
import { Hero } from '../sections/Hero'
import { Plants } from '../sections/Plants'
import { Portfolio } from '../sections/Portfolio'
import '../sections/home.css'
import '../sections/corporate-home.css'
import '../components/cine/cine.css'
import '../sections/company-home.css'
import { useLocation } from 'react-router-dom'
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useReducedMotion } from '../hooks/useMediaQuery'
import { filmPosterUrl } from '../lib/assets'
import { useSite } from '../data/site'

const HomepageMotion = lazy(() => import('../sections/HomepageMotion'))

export function HomePage() {
  const root = useRef<HTMLDivElement>(null)
  const [rootElement, setRootElement] = useState<HTMLDivElement | null>(null)
  const attachRoot = useCallback((element: HTMLDivElement | null) => {
    root.current = element
    setRootElement(element)
  }, [])
  const reducedMotion = useReducedMotion()
  const poster = filmPosterUrl('hero')
  const { data } = useSite()
  const { hash } = useLocation()
  const anchorAllowed = useRef(true)
  const settleAnchor = useCallback(() => {
    if (!anchorAllowed.current || !window.location.hash) return
    const target = document.getElementById(decodeURIComponent(window.location.hash.slice(1)))
    if (target && root.current?.contains(target))
      target.scrollIntoView({ behavior: 'instant', block: 'start' })
  }, [])
  useEffect(() => {
    anchorAllowed.current = Boolean(hash)
    const cancel = () => {
      anchorAllowed.current = false
    }
    const key = (event: KeyboardEvent) => {
      if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', 'Home', 'End', ' '].includes(event.key))
        cancel()
    }
    window.addEventListener('wheel', cancel, { passive: true })
    window.addEventListener('touchmove', cancel, { passive: true })
    window.addEventListener('keydown', key)
    return () => {
      window.removeEventListener('wheel', cancel)
      window.removeEventListener('touchmove', cancel)
      window.removeEventListener('keydown', key)
    }
  }, [hash])
  useEffect(() => {
    if (!data || !hash) return
    const frame = requestAnimationFrame(settleAnchor)
    return () => cancelAnimationFrame(frame)
  }, [data, hash, settleAnchor])
  usePageMeta({
    title: 'Noordveld Machinery B.V. — Built for demanding work',
    description:
      'Industrial and agricultural machinery engineered for performance, reliability and the work that keeps industries moving. Fictional company and demonstration data.',
    path: '/',
  })
  return (
    <div className="corporate-home cinematic-home brand-refresh" ref={attachRoot}>
      {poster ? <link rel="preload" as="image" href={poster} fetchPriority="high" /> : null}
      {!reducedMotion && rootElement ? (
        <Suspense fallback={null}>
          <HomepageMotion root={root} onLayoutReady={settleAnchor} />
        </Suspense>
      ) : null}
      <Hero />
      <CompanyIntroduction />
      <Portfolio />
      <BuiltForWork />
      <Plants />
      <FinalCta />
    </div>
  )
}
