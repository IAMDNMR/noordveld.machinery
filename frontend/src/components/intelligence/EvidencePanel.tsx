import type { QueryResponse } from '../../api'
import { DATA_CLASS_LABEL } from './provenance'

const BY: Record<QueryResponse['understood_by'], string> = { rules: 'Recognised directly', llm: 'Interpreted by the language model', selection: 'Your selection' }

/** The question's route through the system, and the graph edges behind the answer. Collapsed by default; never shows Cypher. */
export function EvidencePanel({ response }: { response: QueryResponse }) {
  const entity = response.entities.map((e) => e.label).join(', ') || 'None needed'
  const steps: [string, string][] = [
    ['Question', response.question],
    ['Intent', `${response.intent_label} (${BY[response.understood_by]})`],
    ['Entity', entity],
    ['Graph path', response.graph_path.length ? response.graph_path.join(' → ') : 'Not applicable'],
    ['Evidence', `${response.evidence.length} relationship${response.evidence.length === 1 ? '' : 's'} read`],
    ['Result', `${response.total} found · answered in ${response.elapsed_ms} ms`],
  ]
  return (
    <details className="evid">
      <summary>How this was answered</summary>
      <ol className="evid__steps">
        {steps.map(([label, value]) => (
          <li key={label}>
            <span className="evid__label">{label}</span>
            <span className="evid__value">{value}</span>
          </li>
        ))}
      </ol>
      {response.evidence.length > 0 ? (
        <div className="evid__table-wrap">
          <table className="evid__table">
            <caption className="sr-only">Evidence read from the graph</caption>
            <thead>
              <tr>
                <th scope="col">From</th>
                <th scope="col">Relationship</th>
                <th scope="col">To</th>
                <th scope="col">Data</th>
              </tr>
            </thead>
            <tbody>
              {response.evidence.map((e, i) => (
                <tr key={`${e.entity}-${e.target}-${i}`}>
                  <td>{e.entity}</td>
                  <td className="mono">{e.relationship}</td>
                  <td>{e.target}</td>
                  <td>{DATA_CLASS_LABEL[e.data_class]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </details>
  )
}
