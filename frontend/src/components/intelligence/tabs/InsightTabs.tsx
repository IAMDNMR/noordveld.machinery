import { useId, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { getPartInsights, getPartProvenance, type PartOverview } from '../../../api'
import { useApi } from '../../../hooks/useApi'
import { formatDate, useIdentification } from '../../../store/identification'
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

/**
 * The next step for this part, by catalogue status. Identification entered here is stored and shown back; it never
 * verifies the part. Only verified catalogue data can change the status.
 */
export function ActionTab({ overview, onOpenFitment }: { overview: PartOverview; onOpenFitment: () => void }) {
  const { record, request, submit } = useIdentification(overview.part_number)
  const store = overview.actions.find((a) => a.kind === 'parts_store')
  const { code, label, reason } = overview.status

  if (store?.href) {
    return (
      <div className="pw-handoff">
        <h3>Ready to order</h3>
        <p>This part is verified and orderable. Pricing, availability and the cart are in the Parts Store.</p>
        <Link className="btn btn-primary" to={store.href}>
          {store.label}
        </Link>
      </div>
    )
  }

  if (code === 'IDENTIFICATION_REQUIRED' || code === 'AMBIGUOUS') {
    return (
      <div className="pw-handoff">
        <h3>{code === 'AMBIGUOUS' ? 'Identify machine / variant / serial' : 'Identify Part'}</h3>
        <p>
          Status: <strong>{label}</strong>. {reason ?? ''} This part cannot be ordered until the identification is verified.
        </p>
        {overview.identification.length > 0 ? (
          <ul className="pw-bullets">
            {overview.identification.map((i, n) => (
              <li key={n}>{[i.model_code, i.needed].filter(Boolean).join(': ')}</li>
            ))}
          </ul>
        ) : null}
        <IdentifyForm
          key={record?.submittedAt ?? 'new'}
          suggestions={overview.identification.map((i) => i.model_code).filter((m): m is string => Boolean(m))}
          initialMachine={record?.machine ?? ''}
          initialSerial={record?.serialOrVariant ?? ''}
          onSubmit={submit}
        />
        {record?.submittedAt ? (
          <div className="pw-saved" role="status">
            <p>
              <strong>Saved {formatDate(record.submittedAt)}:</strong> machine {record.machine || 'not given'}, serial or variant {record.serialOrVariant || 'not given'}.
            </p>
            <p>The status stays {label.toLowerCase()} until this identification is verified against the catalogue.</p>
          </div>
        ) : null}
        <button type="button" className="rcard__action" onClick={onOpenFitment}>
          See machine and fitment details
        </button>
      </div>
    )
  }

  // Unverified
  return (
    <div className="pw-handoff">
      <h3>{record?.requestedAt ? 'Identification requested' : 'Request identification'}</h3>
      <p>
        Status: <strong>{label}</strong>. {reason ?? ''} This part cannot be ordered until it has been identified.
      </p>
      {record?.requestedAt ? (
        <p className="pw-saved" role="status">
          Requested on {formatDate(record.requestedAt)}. The status stays unverified until the part is identified.
        </p>
      ) : (
        <button type="button" className="btn btn-primary" onClick={request}>
          Request identification
        </button>
      )}
    </div>
  )
}

function IdentifyForm({ suggestions, initialMachine, initialSerial, onSubmit }: { suggestions: string[]; initialMachine: string; initialSerial: string; onSubmit: (machine: string, serial: string) => void }) {
  const [machine, setMachine] = useState(initialMachine)
  const [serial, setSerial] = useState(initialSerial)
  const listId = useId()
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (machine.trim() && serial.trim()) onSubmit(machine, serial)
  }
  return (
    <form className="pw-form" onSubmit={submit} aria-label="Identify the part">
      <label>
        <span>Machine model</span>
        <input value={machine} onChange={(e) => setMachine(e.target.value)} list={listId} required maxLength={40} autoComplete="off" />
      </label>
      <datalist id={listId}>
        {suggestions.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </datalist>
      <label>
        <span>Serial number or variant</span>
        <input value={serial} onChange={(e) => setSerial(e.target.value)} required maxLength={60} autoComplete="off" />
      </label>
      <button type="submit" className="btn btn-secondary btn-sm" disabled={!machine.trim() || !serial.trim()}>
        Save identification
      </button>
    </form>
  )
}
