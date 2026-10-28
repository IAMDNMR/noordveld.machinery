import { useId, useState, type FormEvent } from 'react'
import { RecordGraph } from '../components/cine/RecordGraph'
import { SparkLogo } from '../components/spark/SparkLogo'
import '../components/cine/cine.css'
import { ArrowRight } from 'lucide-react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { SparkFilm } from '../components/spark/SparkFilms'
import { BusinessJourney } from '../components/process/BusinessJourney'
import { SPARK_CHAT_ROUTE } from '../data/content'
import { usePageMeta } from '../hooks/usePageMeta'
import '../components/spark/spark-intro.css'
import '../components/spark/spark-intro-redesign.css'

/** The first question, asked from the page: Spark opens with it already on its way. */
function AskSpark() {
  const navigate = useNavigate()
  const inputId = useId()
  const [question, setQuestion] = useState('')
  const ask = (text: string) => {
    if (text.trim())
      navigate(`${SPARK_CHAT_ROUTE}?${new URLSearchParams({ q: text.trim().slice(0, 500) })}`)
  }
  return (
    <div className="sp-ask">
      <form
        className="sp-ask__form"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          ask(question)
        }}
      >
        <label className="sr-only" htmlFor={inputId}>
          Your question for Spark
        </label>
        <input
          id={inputId}
          value={question}
          maxLength={500}
          autoComplete="off"
          placeholder="Ask about a part, a machine or an order"
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button className="sp-button" type="submit" disabled={!question.trim()}>
          Ask Spark
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      </form>
      <Link className="sp-ask__plain" to={SPARK_CHAT_ROUTE}>
        Open Spark without a question
      </Link>
    </div>
  )
}

/** Spark introduction. Each section answers one question a customer actually asks. */
export default function SparkLandingPage() {
  const { pathname } = useLocation()
  const [params] = useSearchParams()
  usePageMeta({
    title: 'Spark',
    description:
      'One conversation for parts, machines, suppliers and orders. Spark checks fitment and supply, shows its evidence and leaves every order for you to confirm.',
    path: '/spark',
  })
  // Earlier conversation links (?q=, ?part=, ?tab=) keep working
  if (['q', 'part', 'tab'].some((key) => params.has(key)))
    return <Navigate to={`${SPARK_CHAT_ROUTE}?${params}`} replace />
  if (pathname !== '/spark') return <Navigate to="/spark" replace />
  return (
    <div className="sp">
      <section className="sp-hero" aria-labelledby="sp-title">
        <div className="sp-frame sp-hero__grid">
          <div className="sp-hero__copy sp-enter" style={{ ['--n' as string]: 0 }}>
            <p className="sp-product-name">
              <SparkLogo size={34} /> Spark · Your parts assistant
            </p>
            <h1 id="sp-title" className="sp-display">
              Clarity for every
              <br />
              <span>parts decision.</span>
            </h1>
            <p className="sp-statement">
              Your parts intelligence and commerce assistant. Find out what fits your machine, who
              supplies it and what you can order, in one conversation.
            </p>
            <AskSpark />
            <a className="sp-text-link" href="#spark-films">
              See how Spark works <ArrowRight size={15} aria-hidden="true" />
            </a>
          </div>
          <div className="sp-hero__showcase sp-enter" style={{ ['--n' as string]: 1 }}>
            <div className="sp-showcase-heading">
              <span>Spark in practice</span>
              <span>Meet the assistant</span>
            </div>
            <SparkFilm film="intro" className="sp-hero__film" />
            <a href="#spark-films" className="sp-showcase-next">
              Explore all three films <ArrowRight size={16} aria-hidden="true" />
            </a>
          </div>
        </div>
      </section>

      <RecordGraph chatRoute={SPARK_CHAT_ROUTE} />

      <BusinessJourney kind="spark" />

      <section className="sp-field sp-reels" id="spark-films" aria-labelledby="sp-films-title">
        <div className="sp-frame">
          <div className="sp-reels__heading">
            <h2 className="sp-h2" id="sp-films-title">
              See the work.
              <br />
              Understand the thinking.
            </h2>
            <p className="sp-body">
              Follow a request from the first question to an order for review, then explore the idea
              behind the experience.
            </p>
          </div>
          <div className="sp-reels__grid">
            <SparkFilm film="workflow" />
            <SparkFilm film="story" />
          </div>
        </div>
      </section>

      <section className="sp-close" aria-labelledby="sp-close">
        <div className="sp-frame sp-close__grid">
          <div>
            <h2 id="sp-close" className="sp-h2">
              Your next question.
              <br />A clearer next step.
            </h2>
            <p className="sp-body">
              Try a question from the demonstration catalogue, or describe your own need.
            </p>
            <p className="sp-small">
              Recorded catalogue evidence and labelled demo commercial data. Missing information
              stays visible; no payment is taken in this demo.
            </p>
          </div>
          <div className="sp-close__action">
            <Link className="sp-button" to={SPARK_CHAT_ROUTE}>
              Start a conversation <ArrowRight size={17} aria-hidden="true" />
            </Link>
            <p className="sp-small">
              Your questions, answers and connections. Together in one workspace.
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}
