import { ArrowUpRight } from 'lucide-react'
import { ButtonLink } from '../components/ButtonLink'
import { BarChart, Donut, NetworkField, StatStrip } from '../components/cine/Cine'
import { AGENTIC_ROUTE, SPARK_CHAT_ROUTE } from '../data/content'
import { useSite } from '../data/site'
import { SparkLogo } from '../components/spark/SparkLogo'
import { Tilt } from '../components/cine/Tilt'
import './insights.css'

/** The catalogue as data: every number is the graph's own count from /site/overview, drawn as it scrolls in. */
export function CatalogueInsights() {
  const { data } = useSite()
  if (!data) return null
  const categories = [...data.partCategories].sort((a, b) => b.count - a.count).slice(0, 8)
  const families = data.families.map((name) => ({
    name,
    value: data.machines.filter((m) => m.family === name).length,
  }))
  return (
    <section id="parts" className="insights cine-dark" aria-labelledby="insights-title">
      <div className="container insights__layout">
        <header className="insights__head">
          <p className="cine-eyebrow">Parts &amp; catalogue</p>
          <h2 id="insights-title">
            Every component, <em>on record.</em>
          </h2>
          <p>
            Machines, parts and the relationships between them live in one connected record. These
            are its current counts.
          </p>
          <StatStrip
            stats={[
              { value: data.partCount, label: 'Parts catalogued' },
              { value: data.partCategories.length, label: 'Part categories' },
              { value: data.machines.length, label: 'Machine models' },
            ]}
          />
          <ButtonLink to="/parts-store">Open Parts Portal</ButtonLink>
        </header>
        <div className="insights__charts">
          <Tilt className="insights__card" max={4}>
            <h3>Largest part categories</h3>
            <BarChart
              label="Parts per category"
              rows={categories.map((c) => ({ name: c.name, value: c.count }))}
            />
          </Tilt>
          <Tilt className="insights__card" max={4}>
            <h3>The range by family</h3>
            <Donut label="Machine models per family" rows={families} total="models" />
          </Tilt>
        </div>
      </div>
    </section>
  )
}

export function SparkTeaser() {
  return (
    <section id="agentic" className="spark-teaser" aria-labelledby="teaser-title">
      <div className="spark-teaser__world" aria-hidden="true">
        <NetworkField nodes={34} seed={11} />
      </div>
      <SparkLogo size={240} className="spark-teaser__logo" />
      <div className="container spark-teaser__inner">
        <p className="cine-eyebrow">Ask Spark</p>
        <h2 id="teaser-title">
          A little clarity.
          <br />
          <em>A lot of possibility.</em>
        </h2>
        <p className="spark-teaser__lead">
          One conversation over the same connected record: parts, fitment, suppliers, dealers and
          buying options, with the evidence behind every answer.
        </p>
        <div className="spark-teaser__prompts">
          {[
            ['Find a compatible part for my machine', 'Find a compatible part'],
            ['Help me explore how parts and machines connect', 'See how parts connect'],
            ['Where is my last order?', 'Follow an order'],
          ].map(([question, label]) => (
            <a key={label} href={`${SPARK_CHAT_ROUTE}?q=${encodeURIComponent(question)}`}>
              {label}
              <ArrowUpRight size={16} aria-hidden="true" />
            </a>
          ))}
        </div>
        <ButtonLink to={AGENTIC_ROUTE}>Meet Spark</ButtonLink>
      </div>
    </section>
  )
}
