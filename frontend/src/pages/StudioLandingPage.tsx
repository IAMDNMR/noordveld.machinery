import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Check,
  Database,
  Film,
  GitBranch,
  MessageSquare,
  Monitor,
  Sparkles,
} from 'lucide-react'
import { usePageMeta } from '../hooks/usePageMeta'
import './StudioLandingPage.css'
const chapters = [
  [
    'THE EVERYDAY',
    'Every great application starts with a real problem.',
    'Requests in email. Plans in spreadsheets. Updates in someone’s head. Your team makes it work. Imagine giving them something that works for them.',
    'There has to be a better way.',
  ],
  [
    'YOUR IDEA',
    'You tell the story. The Studio finds the structure.',
    'Describe what your team needs in your own words. The Studio turns that conversation into a first requirements draft, ready for your review.',
    'We need one place to manage deliveries.',
  ],
  [
    'THE UNDERSTANDING',
    'Business knowledge connects the dots.',
    'Stored domain knowledge helps shape the roles, records and rules behind your idea. Missing details become proposed assumptions you can review.',
    'A delivery connects a request, a driver and a destination.',
  ],
  [
    'THE DESIGN',
    'Piece by piece, your application takes shape.',
    'A clear process becomes connected data, purposeful screens and business rules. Each stage builds on the one you have reviewed.',
    'Now everyone knows what happens next.',
  ],
  [
    'YOUR SAY',
    'A thoughtful pause. Then the next chapter.',
    'Review the draft. Ask for a change, or say “continue.” The Studio moves forward one stage at a time, with you in control of the direction.',
    'Looks good. Let’s continue.',
  ],
]
export default function StudioLandingPage() {
  const [active, setActive] = useState(0)
  usePageMeta({
    title: 'Design Studio',
    description: 'From business idea to connected application design. Follow the story.',
    path: '/studio',
  })
  useEffect(() => {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>('[data-chapter]'))
    const update = () => {
      const target = window.innerHeight * (window.innerWidth <= 650 ? 0.8 : 0.5)
      const closest = nodes.reduce(
        (best, node) => {
          const rect = node.getBoundingClientRect()
          const distance = Math.abs(rect.top + rect.height / 2 - target)
          return distance < best.distance ? { index: Number(node.dataset.chapter), distance } : best
        },
        { index: 0, distance: Infinity },
      )
      setActive(closest.index)
    }
    window.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    update()
    return () => {
      window.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [])
  return (
    <div className="sl-page">
      <section className="sl-hero">
        <span className="sl-eyebrow">
          <Sparkles size={14} /> NOORDVELD DESIGN STUDIO
        </span>
        <h1>
          Behind every better business
          <br />
          is an idea <em>worth building.</em>
        </h1>
        <p>
          You know what your team needs. Let’s turn that knowledge
          <br /> into the application that moves them forward.
        </p>
        <div className="sl-actions">
          <Link className="sl-primary" to="/design-studio">
            Open Design Studio <ArrowRight size={17} />
          </Link>
          <Link className="sl-text-link" to="/design-studio/demo">
            Explore the demo <ArrowRight size={17} />
          </Link>
          <a className="sl-text-link" href="#studio-story">
            Follow the story ↓
          </a>
        </div>
        <div className="sl-hero-note">From a conversation to a connected application design.</div>
        <div className="sl-thread" aria-hidden="true">
          <span>YOUR IDEA</span>
          <i />
          <MessageSquare />
          <i />
          <Database />
          <i />
          <Monitor />
          <i />
          <span>WHAT’S NEXT</span>
        </div>
        <div className="sl-index">
          A LITTLE IMAGINATION. A CLEAR WAY FORWARD.<span>SCROLL TO DISCOVER ↓</span>
        </div>
      </section>
      <section
        className="sl-story"
        id="studio-story"
        aria-label="How an idea becomes an application"
      >
        <div className="sl-story-visual">
          <div className="sl-scene">
            <div className="sl-scene-bar">
              <span>
                <Sparkles size={14} /> THE MAKING OF AN APPLICATION
              </span>
              <small>Illustrative example</small>
            </div>
            <div className="sl-scene-content" key={active}>
              <span className="sl-eyebrow">A DELIVERY TEAM’S STORY</span>
              {active === 0 ? (
                <div className="sl-scattered">
                  <div>
                    ↗ INBOX<strong>Where is my delivery?</strong>
                    <small>12 new messages</small>
                  </div>
                  <div>
                    ▦ delivery_plan_v4.xlsx<strong>Which version is right?</strong>
                    <small>Last edited yesterday</small>
                  </div>
                  <div>
                    ☏ TEAM CHAT<strong>Has anyone assigned a driver?</strong>
                    <small>3 unread replies</small>
                  </div>
                </div>
              ) : active === 1 ? (
                <div className="sl-conversation">
                  <small>YOU</small>
                  <p>
                    “We need one place to manage deliveries, assign drivers and keep customers
                    updated.”
                  </p>
                  <small>DESIGN STUDIO</small>
                  <strong>A clearer starting point.</strong>
                  {[
                    'Manage delivery requests',
                    'Assign drivers and track progress',
                    'Keep customers informed',
                  ].map((t) => (
                    <span key={t}>
                      <Check size={14} />
                      {t}
                    </span>
                  ))}
                </div>
              ) : active === 2 ? (
                <div className="sl-knowledge">
                  <Database size={30} />
                  <h3>Domain knowledge</h3>
                  <small>Connected reference knowledge</small>
                  <div>
                    {[
                      'People & roles',
                      'Business rules',
                      'Delivery records',
                      'Process patterns',
                    ].map((t) => (
                      <span key={t}>{t}</span>
                    ))}
                  </div>
                  <p>Knowledge + your context → a draft for your business</p>
                </div>
              ) : active === 3 ? (
                <div className="sl-blueprint">
                  <div className="sl-flow">
                    {['Request', 'Assign', 'Deliver'].map((t) => (
                      <span key={t}>
                        <GitBranch size={18} />
                        {t}
                      </span>
                    ))}
                  </div>
                  <div className="sl-models">
                    <div>
                      <Database size={19} />
                      <strong>Connected data</strong>
                      <span>Customer → Delivery</span>
                      <span>Driver → Assignment</span>
                      <span>Delivery → Status</span>
                    </div>
                    <div>
                      <Monitor size={19} />
                      <strong>Delivery workspace</strong>
                      <div className="sl-screen">
                        <i />
                        <i />
                        <i />
                        <i />
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="sl-review">
                  <span className="sl-check">
                    <Check size={30} />
                  </span>
                  <h3>A stage ready for your review.</h3>
                  <p>
                    Your requirements are drafted.
                    <br />
                    Take a look before the next step.
                  </p>
                  <span className="sl-review-button">
                    Looks good, continue <ArrowRight size={14} />
                  </span>
                  <small>Or ask the Studio to make a change.</small>
                </div>
              )}
            </div>
            <div className="sl-scene-bar sl-scene-bottom">
              <span>ONE IDEA. A CONNECTED DESIGN.</span>
              <span>0{active + 1} / 05</span>
            </div>
          </div>
          <nav className="sl-chapter-nav" aria-label="Story chapters">
            {chapters.map((c, i) => (
              <a
                key={c[0]}
                href={`#chapter-${i}`}
                aria-current={active === i ? 'step' : undefined}
                onClick={() => setActive(i)}
              >
                <span>0{i + 1}</span>
                {c[0]}
              </a>
            ))}
          </nav>
        </div>
        <div className="sl-chapters">
          {chapters.map((c, i) => (
            <article
              key={c[0]}
              id={`chapter-${i}`}
              data-chapter={i}
              className={active === i ? 'is-active' : ''}
            >
              <span className="sl-eyebrow">
                0{i + 1} / {c[0]}
              </span>
              <h2>{c[1]}</h2>
              <p>{c[2]}</p>
              <blockquote>“{c[3]}”</blockquote>
            </article>
          ))}
        </div>
      </section>
      <section className="sl-bridge">
        <span className="sl-eyebrow">THE BIG PICTURE</span>
        <h2>
          Your idea doesn’t have to arrive finished.
          <br />
          <em>That’s what the journey is for.</em>
        </h2>
        <p>Start with a problem. Shape the solution. Review each chapter.</p>
      </section>
      <section className="sl-demo" id="studio-demo">
        <div className="sl-demo-heading">
          <div>
            <span className="sl-eyebrow">THE STORY, IN MOTION</span>
            <h2>A closer look at what’s possible.</h2>
          </div>
          <p>A home for your upcoming demo film.</p>
        </div>
        <div
          className="sl-video-placeholder"
          role="img"
          aria-label="Reserved space for the upcoming Design Studio demo video"
        >
          <div className="sl-video-orbit" />
          <Film size={34} strokeWidth={1.25} />
          <strong>Every idea has a story.</strong>
          <p>Soon, you’ll see this one come to life.</p>
          <span>DESIGN STUDIO · DEMO FILM COMING SOON</span>
        </div>
      </section>
      <section className="sl-finale">
        <span className="sl-eyebrow">NOW IT’S YOUR TURN</span>
        <h2>
          What’s the story
          <br />
          <em>you want to change?</em>
        </h2>
        <p>Bring a challenge. An ambition. Even a “what if.”</p>
        <Link className="sl-primary" to="/design-studio">
          Open Design Studio <ArrowRight size={17} />
        </Link>
        <small>Local demo access · No new account needed</small>
      </section>
    </div>
  )
}
