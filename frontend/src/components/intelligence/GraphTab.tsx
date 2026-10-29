import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { askQuestion, getEntity, getPartGraph } from '../../api/index'
import { useApi } from '../../hooks/useApi'
import { ProvenanceBadge } from './provenance'
import { TabFrame } from './tabs/shared'
import { GraphExplorer } from './GraphExplorer'
import { evidenceGraph } from './graphModel'

export function GraphTab({ partKey, onOpen }: { partKey: string; onOpen: (part: string) => void }) {
  const [params] = useSearchParams()
  const question = params.get('q') || ''
  const [all, setAll] = useState(!question)
  return (
    <div>
      {question ? (
        <div className="gx-scope">
          <div>
            <strong>{all ? 'All part connections' : 'Answer relationships'}</strong>
            <p>{question}</p>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setAll((value) => !value)}
          >
            {all ? 'Show answer relationships' : 'Show all part connections'}
          </button>
        </div>
      ) : null}
      {all ? (
        <PartGraph key={partKey} partKey={partKey} onOpen={onOpen} />
      ) : (
        <AnswerGraph key={question} question={question} onOpen={onOpen} />
      )}
    </div>
  )
}
function PartGraph({ partKey, onOpen }: { partKey: string; onOpen: (part: string) => void }) {
  const state = useApi((signal) => getPartGraph(partKey, signal), `graph:${partKey}`)
  return (
    <TabFrame state={state} label="Relationships">
      {(view) => (
        <GraphExplorer
          view={view}
          onOpen={onOpen}
          preferOne
          renderDetail={(node) =>
            node.kind !== 'PART' ? <NodeDetail key={node.id} nodeId={node.id} /> : null
          }
        />
      )}
    </TabFrame>
  )
}
function AnswerGraph({ question, onOpen }: { question: string; onOpen: (part: string) => void }) {
  const state = useApi(
    (signal) => askQuestion(question, [], 12, signal),
    `answer-graph:${question}`,
  )
  return (
    <TabFrame state={state} label="Answer relationships">
      {(response) => (
        <GraphExplorer
          view={evidenceGraph(response.evidence)}
          onOpen={onOpen}
          label="Answer relationships"
        />
      )}
    </TabFrame>
  )
}

/** The stored detail of a node that is not a part, loaded when the node is selected. */
function NodeDetail({ nodeId }: { nodeId: string }) {
  const [kind, id] = [nodeId.slice(0, nodeId.indexOf(':')), nodeId.slice(nodeId.indexOf(':') + 1)]
  const detail = useApi((s) => getEntity(kind, id, s), `entity:${nodeId}`)
  const navigate = useNavigate()
  return (
    <div className="pg__detail">
      <TabFrame state={detail} label="Detail">
        {(d) => (
          <>
            {d.subtitle ? <p className="pw-rows__sub">{d.subtitle}</p> : null}
            <dl className="pw-facts">
              {d.facts.map((f) => (
                <div key={f.label}>
                  <dt>{f.label}</dt>
                  <dd className={f.value ? undefined : 'is-missing'}>
                    {f.value ?? 'Not available'}
                  </dd>
                </div>
              ))}
              <div>
                <dt>Data</dt>
                <dd>
                  <ProvenanceBadge value={d.data_class} />
                </dd>
              </div>
            </dl>
            {d.links.length > 0 ? (
              <div className="pg__links">
                {d.links.map((l) =>
                  l.href ? (
                    <Link key={l.label} className="rcard__action" to={l.href}>
                      {l.label}
                    </Link>
                  ) : l.question ? (
                    <button
                      key={l.label}
                      type="button"
                      className="rcard__action"
                      onClick={() => navigate(`/spark/chat?q=${encodeURIComponent(l.question!)}`)}
                    >
                      {l.label}
                    </button>
                  ) : null,
                )}
              </div>
            ) : null}
          </>
        )}
      </TabFrame>
    </div>
  )
}
