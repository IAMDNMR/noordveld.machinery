import { useState } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { getAgentSuggestions } from '../../../../src/api/agent'
import { useApi } from '../../../../src/hooks/useApi'
import './demo-requests.css'

/** Real catalogue requests link to the running shopping workflow; the film never invents an operational result. */
export function DemoRequests() {
  const suggestions = useApi((signal) => getAgentSuggestions(signal), 'commerce-intro-examples')
  const [expanded, setExpanded] = useState(false)
  const rows = suggestions.data ?? []
  return (
    <section className="agentic-examples" aria-labelledby="commerce-examples-title">
      <div className="container">
        <div className="agentic-examples__intro">
          <div>
            <p className="eyebrow">See it work</p>
            <h2 id="commerce-examples-title">
              Start with a need.
              <br />
              Explore the options.
            </h2>
            <p>Try a request from the Noordveld demonstration catalogue, or describe your own.</p>
          </div>
          <a href="/agentic-shopping">
            Try your own request <ArrowUpRight size={18} aria-hidden="true" />
          </a>
        </div>
        {suggestions.loading ? <p role="status">Loading example requests…</p> : null}
        {suggestions.error ? (
          <p>
            Example requests are unavailable. You can still open Agentic Shopping and enter a
            request.
          </p>
        ) : null}
        <ul className="agentic-examples__grid">
          {rows.slice(0, expanded ? undefined : 4).map((item) => (
            <li key={item.request}>
              <a href={`/agentic-shopping?${new URLSearchParams({ q: item.request })}`}>
                <span>{item.action}</span>
                <h3>{item.need}</h3>
                <p>{item.request}</p>
                <ArrowUpRight size={18} aria-hidden="true" />
              </a>
            </li>
          ))}
        </ul>
        {rows.length > 4 ? (
          <button type="button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
            {expanded ? 'Show fewer examples' : `Explore all ${rows.length} examples`}
          </button>
        ) : null}
        <p className="agentic-examples__note">
          Prices, availability and fulfilment data are synthetic. Requests prepare options for
          review; they do not place an order.
        </p>
      </div>
    </section>
  )
}
