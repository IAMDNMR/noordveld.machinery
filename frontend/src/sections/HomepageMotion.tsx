import type { RefObject } from 'react'
import { useGSAP } from '@gsap/react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useSite } from '../data/site'

gsap.registerPlugin(useGSAP, ScrollTrigger)

/** Loaded only by the homepage. All triggers belong to a scoped React/GSAP context. */
export default function HomepageMotion({
  root,
  onLayoutReady,
}: {
  root: RefObject<HTMLDivElement | null>
  onLayoutReady: () => void
}) {
  const { data } = useSite()

  useGSAP(
    () => {
      const element = root.current
      if (!element) return
      const media = gsap.matchMedia()
      media.add(
        {
          desktop: '(min-width: 1100px) and (min-height: 650px)',
          reduced: '(prefers-reduced-motion: reduce)',
        },
        (context) => {
          if (context.conditions?.reduced) return
          const select = gsap.utils.selector(element)
          if (window.scrollY < 80) {
            gsap
              .timeline({ defaults: { ease: 'power3.out' } })
              .fromTo(select('.hero__label'), { opacity: 0 }, { opacity: 0.8, duration: 0.6 })
              .fromTo(
                select('.hero__line > span'),
                { yPercent: 110 },
                { yPercent: 0, duration: 0.9, stagger: 0.12 },
                0.12,
              )
              .fromTo(
                select('.hero__lead, .hero__actions'),
                { opacity: 0, y: 12 },
                { opacity: 1, y: 0, duration: 0.65, stagger: 0.1 },
                0.55,
              )
              .fromTo(select('.hero__foot'), { opacity: 0 }, { opacity: 1, duration: 0.6 }, 0.9)
          }
          if (!context.conditions?.desktop) return
          gsap.set(element, { attr: { 'data-motion': 'desktop' } })
          gsap.fromTo(
            select('.company-introduction__statement'),
            { y: 35 },
            {
              y: 0,
              ease: 'none',
              scrollTrigger: {
                trigger: select('.company-introduction')[0],
                start: 'top 90%',
                end: 'top 35%',
                scrub: 0.5,
              },
            },
          )
          gsap.fromTo(
            select('.company-introduction__film .film__video'),
            { scale: 1.08 },
            {
              scale: 1,
              ease: 'none',
              scrollTrigger: {
                trigger: select('.company-introduction__film')[0],
                start: 'top bottom',
                end: 'bottom center',
                scrub: 0.5,
              },
            },
          )
          gsap.fromTo(
            select('.hero__copy'),
            { y: 0, opacity: 1 },
            {
              y: -50,
              opacity: 0,
              ease: 'none',
              scrollTrigger: {
                trigger: select('.hero')[0],
                start: 'top top',
                end: 'bottom 25%',
                scrub: 0.5,
              },
            },
          )
          gsap.to(select('.hero__film .film__video'), {
            scale: 1.05,
            ease: 'none',
            scrollTrigger: {
              trigger: select('.hero')[0],
              start: 'top top',
              end: 'bottom top',
              scrub: 0.5,
            },
          })

          const scene = select('.built__stage')[0]
          gsap
            .timeline({
              scrollTrigger: {
                trigger: scene,
                pin: scene,
                start: 'top top+=72',
                end: () => `+=${Math.round(window.innerHeight * 0.5)}`,
                scrub: 0.5,
                invalidateOnRefresh: true,
                anticipatePin: 1,
              },
            })
            .fromTo(
              select('.built__window .film__video'),
              { clipPath: 'inset(16% 14% 15% 14%)' },
              { clipPath: 'inset(0% 0% 0% 0%)', duration: 1, ease: 'none' },
              0,
            )
            .to(select('.built__intro'), { y: -30, opacity: 0, duration: 0.5, ease: 'none' }, 0.2)
            .fromTo(
              select('.built__caption'),
              { opacity: 0, y: 8 },
              { opacity: 1, y: 0, duration: 0.3 },
              0.65,
            )

          gsap.fromTo(
            select('.final__copy h2'),
            { y: 24 },
            {
              y: 0,
              ease: 'none',
              scrollTrigger: {
                trigger: select('.final')[0],
                start: 'top 95%',
                end: 'top 65%',
                scrub: 0.4,
              },
            },
          )
          return () => element.removeAttribute('data-motion')
        },
      )

      // Only layout changes request a refresh; nothing reads layout on every scroll frame.
      let refreshTimer: ReturnType<typeof setTimeout>
      const resize = new ResizeObserver(() => {
        if (element.getAttribute('data-motion') !== 'desktop') return
        clearTimeout(refreshTimer)
        refreshTimer = setTimeout(() => {
          if (element.getAttribute('data-motion') === 'desktop') ScrollTrigger.refresh()
        }, 180)
      })
      resize.observe(element)
      const frame = requestAnimationFrame(onLayoutReady)
      return () => {
        cancelAnimationFrame(frame)
        clearTimeout(refreshTimer)
        resize.disconnect()
        media.revert()
      }
    },
    { scope: root },
  )

  useGSAP(
    () => {
      if (!data || !root.current) return
      const media = gsap.matchMedia()
      media.add('(min-width: 1100px) and (prefers-reduced-motion: no-preference)', () => {
        const select = gsap.utils.selector(root.current)
        const product = select('.product-theatre')[0]
        if (product) {
          const trigger = { trigger: product, start: 'top 85%', end: 'top 30%', scrub: 0.5 }
          gsap.fromTo(
            select('.product-theatre__model'),
            { y: 30, opacity: 0.5 },
            { y: 0, opacity: 1, ease: 'none', scrollTrigger: trigger },
          )
          gsap.fromTo(
            select('.product-theatre__visual .mimg'),
            { clipPath: 'inset(8% 0% 8% 0%)' },
            { clipPath: 'inset(0% 0% 0% 0%)', ease: 'none', scrollTrigger: trigger },
          )
          gsap.fromTo(
            select('.product-theatre__visual img'),
            { scale: 1.07 },
            { scale: 1, ease: 'none', scrollTrigger: trigger },
          )
        }
      })
      ScrollTrigger.refresh()
      const frame = requestAnimationFrame(onLayoutReady)
      return () => {
        cancelAnimationFrame(frame)
        media.revert()
      }
    },
    { scope: root, dependencies: [data], revertOnUpdate: true },
  )

  return null
}
