import { useRef, useState, type CSSProperties } from 'react'
import { ArrowUpRight, Cog, Network, PackageSearch, Wrench } from 'lucide-react'
import { Link } from 'react-router-dom'
import { editorialImageUrl } from '../lib/assets'
import { useMediaQuery, useReducedMotion } from '../hooks/useMediaQuery'
import { useStickyProgress } from '../components/cine/useScrollProgress'
import '../components/cine/cine.css'
import './lifecycle.css'

const chapters = [
  {
    name: 'Choose',
    icon: Cog,
    title: 'Find your machine.',
    description:
      'Explore the machinery range, compare specifications and understand where each model belongs.',
    image: 'machinery-at-work',
    to: '/machines',
    action: 'Explore the range',
  },
  {
    name: 'Maintain',
    icon: Wrench,
    title: 'Keep the work moving.',
    description:
      'Connect the machine, dealer and service team. Follow the hand-offs that keep equipment supported through its working life.',
    image: 'service',
    to: '/parts-services',
    action: 'Explore Aftersales',
  },
  {
    name: 'Source',
    icon: PackageSearch,
    title: 'The right part. One place.',
    description:
      'Search by machine or part, check recorded fitment and review availability before making your choice.',
    image: 'mechanical-detail',
    to: '/parts-store',
    action: 'Open Parts Portal',
  },
  {
    name: 'Understand',
    icon: Network,
    title: 'Ask the next question.',
    description:
      'Talk to Spark about parts, suppliers and buying options. Explore the evidence and see how the records connect.',
    image: 'engineering',
    to: '/spark',
    action: 'Meet Spark',
  },
]

/**
 * The ownership lifecycle as one scroll-driven scene. On wide screens the section is a tall track with a sticky frame: scrolling moves
 * through the four chapters, draws the lifecycle line and cross-fades the pictures. The tabs stay a real, keyboard-operable tablist, and on
 * phones or with reduced motion the same tabs are simply clicked.
 */
export function OwnershipJourney() {
  const track = useRef<HTMLElement>(null)
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  const wide = useMediaQuery('(min-width: 1100px) and (min-height: 640px)')
  const reduced = useReducedMotion()
  const scrolling = wide && !reduced
  const progress = useStickyProgress(track)
  const [picked, setPicked] = useState<{ index: number; at: number } | null>(null)
  const fromScroll = Math.min(chapters.length - 1, Math.floor(progress * chapters.length * 0.999))
  // A click wins until the reader scrolls on; without the scroll scene the click is the only control.
  const active =
    picked && (!scrolling || Math.abs(progress - picked.at) < 0.06)
      ? picked.index
      : scrolling
        ? fromScroll
        : (picked?.index ?? 0)
  const choose = (index: number) => setPicked({ index, at: progress })
  const chapter = chapters[active]
  return (
    <section
      ref={track}
      className={`lifecycle${scrolling ? ' is-scrolling' : ''}`}
      aria-labelledby="ownership-title"
      style={{ '--p': scrolling ? progress : (active + 1) / chapters.length } as CSSProperties}
    >
      <div className="lifecycle__frame">
        <div className="lifecycle__media" aria-hidden="true">
          {chapters.map((item, index) => {
            const src = editorialImageUrl(item.image)
            return src ? (
              <img
                key={item.image}
                src={src}
                alt=""
                loading="lazy"
                className={index === active ? 'is-active' : ''}
              />
            ) : null
          })}
          <span className="lifecycle__veil" />
          <span className="lifecycle__count">
            0{active + 1}
            <small> / 0{chapters.length}</small>
          </span>
        </div>
        <div className="container lifecycle__layout">
          <header>
            <p className="cine-eyebrow">The ownership lifecycle</p>
            <h2 id="ownership-title">
              Built for the job.
              <br />
              <em>Supported for the journey.</em>
            </h2>
          </header>
          <div className="lifecycle__rail" aria-hidden="true">
            <svg viewBox="0 0 400 16" preserveAspectRatio="none">
              <line className="lifecycle__base" x1="0" y1="8" x2="400" y2="8" />
              <line className="lifecycle__fill" x1="0" y1="8" x2="400" y2="8" pathLength={1} />
            </svg>
          </div>
          <div
            className="lifecycle__tabs"
            role="tablist"
            aria-label="Explore the ownership journey"
          >
            {chapters.map((item, index) => {
              const Icon = item.icon
              return (
                <button
                  key={item.name}
                  ref={(node) => {
                    tabs.current[index] = node
                  }}
                  type="button"
                  role="tab"
                  id={`ownership-tab-${index}`}
                  aria-selected={active === index}
                  aria-controls="ownership-panel"
                  tabIndex={active === index ? 0 : -1}
                  className={index < active ? 'is-done' : undefined}
                  onClick={() => choose(index)}
                  onKeyDown={(event) => {
                    const next =
                      event.key === 'ArrowRight'
                        ? (index + 1) % chapters.length
                        : event.key === 'ArrowLeft'
                          ? (index + chapters.length - 1) % chapters.length
                          : event.key === 'Home'
                            ? 0
                            : event.key === 'End'
                              ? chapters.length - 1
                              : null
                    if (next === null) return
                    event.preventDefault()
                    choose(next)
                    tabs.current[next]?.focus()
                  }}
                >
                  <i>
                    <Icon size={18} aria-hidden="true" />
                  </i>
                  <span>0{index + 1}</span>
                  {item.name}
                </button>
              )
            })}
          </div>
          <div
            id="ownership-panel"
            role="tabpanel"
            aria-labelledby={`ownership-tab-${active}`}
            className="lifecycle__panel"
            tabIndex={0}
          >
            <div key={chapter.name} className="lifecycle__copy">
              <h3>{chapter.title}</h3>
              <p>{chapter.description}</p>
              <Link to={chapter.to}>
                {chapter.action}
                <ArrowUpRight size={20} aria-hidden="true" />
              </Link>
            </div>
          </div>
          {scrolling ? (
            <p className="lifecycle__hint">Scroll to move through the lifecycle</p>
          ) : null}
        </div>
      </div>
    </section>
  )
}
