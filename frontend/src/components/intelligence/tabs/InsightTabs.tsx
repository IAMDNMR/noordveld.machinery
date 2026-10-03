import { Link } from 'react-router-dom'
import { getPartInsights, getPartProvenance, type PartOverview } from '../../../api'
import { useApi } from '../../../hooks/useApi'
import { humanize } from '../../../lib/format'
import { DATA_CLASS_MEANING, ProvenanceBadge } from '../provenance'
import { Facts, TabFrame } from './shared'

export function ProvenanceTab({ partKey }: { partKey: string }) {
  const state = useApi((s) => getPartProvenance(partKey, s), `provenance:${partKey}`)
  return (
    <TabFrame state={state} label="Provenance">
      {(p) => (
        <>
          <Facts
            rows={[
              ['Data classification', <ProvenanceBadge value={p.classification} key="c" />],
              ['Meaning', DATA_CLASS_MEANING[p.classification]],
              ['Source', p.source_name],
              ['Source file', p.source_file],
              ['Source sheet', p.source_sheet],
              ['Source record', p.source_record_id],
              ['Confidence', p.confidence],
              ['Verification', p.verification],
              ['Authoritative for ordering', p.authoritative ? 'Yes' : 'No'],
              ['Last updated', p.last_updated],
            ]}
          />
          <h3 className="pw-sub">Where each relationship comes from</h3>
          <div className="evid__table-wrap">
            <table className="evid__table">
              <thead>
                <tr>
                  <th scope="col">Relationship</th>
                  <th scope="col">Connected to</th>
                  <th scope="col">Count</th>
                  <th scope="col">Data</th>
                </tr>
              </thead>
              <tbody>
                {p.relationship_sources.map((r, i) => (
                  <tr key={i}>
                    <td className="mono">{r.relationship}</td>
                    <td>{r.connected_label}</td>
                    <td>{r.count}</td>
                    <td>
                      <ProvenanceBadge value={r.data_class} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 className="pw-sub">Known limitations</h3>
          <ul className="pw-bullets">
            {p.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </>
      )}
    </TabFrame>
  )
}

export function InsightsTab({ partKey }: { partKey: string }) {
  const state = useApi((s) => getPartInsights(partKey, s), `insights:${partKey}`)
  return (
    <>
      <p className="pw-lead">Counted from the graph. These figures are calculated, not generated.</p>
      <TabFrame state={state} label="Insights">
        {(rows) => (
          <ul className="pi-insights">
            {rows.map((i) => (
              <li key={i.key} className={`is-${i.state}`}>
                <p className="pi-insights__label">{i.label}</p>
                <p className="pi-insights__value">{i.value === null ? 'Not connected' : i.value}</p>
                {i.detail ? <p className="pi-insights__detail">{i.detail}</p> : null}
                <p className="pi-insights__state">{i.state === 'gap' ? 'No relationship recorded' : i.state === 'not_connected' ? 'Not connected' : ''}</p>
              </li>
            ))}
          </ul>
        )}
      </TabFrame>
    </>
  )
}

/** The hand-off to the transactional store: offered only when the part is verified and orderable. */
export function StoreTab({ overview, onIdentify }: { overview: PartOverview; onIdentify: () => void }) {
  const store = overview.actions.find((a) => a.kind === 'parts_store')
  if (store?.href) {
    return (
      <div className="pw-handoff">
        <h3>Ready to order</h3>
        <p>This part is verified and orderable. Pricing, availability and the cart are in the Parts Store.</p>
        <Link className="button button--primary" to={store.href}>
          {store.label}
        </Link>
      </div>
    )
  }
  if (overview.status.code === 'IDENTIFICATION_REQUIRED') {
    return (
      <div className="pw-handoff">
        <h3>Identification required first</h3>
        <p>The machine or serial range has to be confirmed before this part can be ordered. Check the machine and fitment details.</p>
        <button type="button" className="button button--primary" onClick={onIdentify}>
          Identify part
        </button>
      </div>
    )
  }
  return (
    <div className="pw-handoff">
      <h3>Not available to order</h3>
      <p>
        This part is {overview.status.label.toLowerCase()}
        {overview.orderable === false ? ' and cannot be ordered online' : overview.orderable === null ? ' and online ordering is not configured' : ''}. Review its provenance to see what would verify it.
      </p>
      <p className="pw-note-inline">Status: {humanize(overview.status.code)}</p>
    </div>
  )
}
