import type { ReactNode } from 'react'
import type {
  AgentResponse,
  CommerceContext,
  PartLookupContext,
  Confidence,
  DataRef,
  DiscoveryContext,
  Domain,
  EvidenceItem,
  LogisticsContext,
  PathStep,
  RouteOptionsContext,
  WarrantyContext,
} from '../../api/commerce'

/**
 * Presentational views over the Commerce API responses. They format what the backend returned and add no rule: no status is computed, no part is ranked, no warranty
 * reason is written here. A field the role may not see is absent from the response, and these views simply do not show it.
 */
const label = (code: string | null | undefined): string =>
  (code ?? 'not recorded').replace(/_/g, ' ').toLowerCase()
const days = (n: number | null | undefined): string =>
  n == null ? 'not recorded' : `${Math.abs(n)} ${Math.abs(n) === 1 ? 'day' : 'days'}`
const money = (
  price:
    | { state: string; unit_price?: number; currency?: string; price_status?: string }
    | null
    | undefined,
): string | null =>
  price && price.state === 'AVAILABLE' && price.unit_price != null
    ? `${price.unit_price.toFixed(2)} ${price.currency ?? ''}${price.price_status ? ` (${label(price.price_status)})` : ''}`.trim()
    : null

const TONE: Record<string, string> = {
  SUCCESS: 'ok',
  RECOMMEND: 'ok',
  ELIGIBLE: 'ok',
  TRACKED: 'ok',
  DELIVERED: 'ok',
  PASS: 'ok',
  NOT_ELIGIBLE: 'bad',
  FAIL: 'bad',
  REJECTED: 'bad',
  REQUIRES_REVIEW: 'warn',
  REQUIRES_CLARIFICATION: 'warn',
  INSUFFICIENT_DATA: 'warn',
  UNKNOWN: 'warn',
  NOT_FOUND: 'warn',
  NO_AVAILABLE_RECOMMENDATION: 'warn',
  NO_VALID_RECOMMENDATION: 'warn',
}

export function Chip({ value, children }: { value: string; children?: ReactNode }) {
  return (
    <span className={`cw-chip cw-chip--${TONE[value] ?? 'neutral'}`}>
      {children ?? label(value)}
    </span>
  )
}

export function Banner({ ctx }: { ctx: CommerceContext }) {
  const d = ctx.decision
  return (
    <div
      className={`cw-banner cw-banner--${TONE[d.decision] ?? TONE[d.status] ?? 'neutral'}`}
      role="status"
    >
      <div className="cw-banner__head">
        <Chip value={d.decision} />
        <Chip value={d.status}>{label(d.status)}</Chip>
      </div>
      <p className="cw-banner__summary">{d.summary}</p>
      {/* decision.recommended_next_action is an instruction for the agent, not wording for the user, so it is not shown */}
    </div>
  )
}

export function Options({
  options,
  onPick,
}: {
  options: Record<string, unknown>[]
  onPick?: (option: Record<string, unknown>) => void
}) {
  if (!options.length) return null
  return (
    <ul className="cw-options" aria-label="Options">
      {options.slice(0, 12).map((o, i) => {
        const text = Object.entries(o)
          .filter(([, v]) => v != null && v !== '' && !(Array.isArray(v) && v.length === 0))
          .map(
            ([k, v]) =>
              `${label(k)}: ${Array.isArray(v) ? v.map((x) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join(', ') : String(v)}`,
          )
          .join(' · ')
        return (
          <li key={i}>
            <span>{text}</span>
            {onPick && (
              <button type="button" className="cw-link" onClick={() => onPick(o)}>
                Use this
              </button>
            )}
          </li>
        )
      })}
    </ul>
  )
}

// ── discovery ────────────────────────────────────────────────────────────────────────────────────
/** `bare`: inside the unified answer, where the lead sentence already says the decision and a clarification is asked in the conversation, so neither is repeated here. */
export function DiscoveryView({
  ctx,
  onPick,
  bare,
}: {
  ctx: DiscoveryContext
  onPick?: (o: Record<string, unknown>) => void
  bare?: boolean
}) {
  const part = ctx.recommended_part ?? ctx.compatible_part
  const rejected = Object.entries(ctx.rejection_reasons ?? {})
  const nameOf = (id: string) => ctx.candidate_parts.find((p) => p.part_id === id)
  const avail = part ? ctx.availability.find((a) => a.part_id === part.part_id) : undefined
  return (
    <section className="cw-view" aria-label="Part discovery result">
      {!bare && <Banner ctx={ctx} />}
      {ctx.machine && ctx.machine.resolution === 'RESOLVED' && (
        <p className="cw-meta">
          Machine: {ctx.machine.name ?? ctx.machine.model} ({ctx.machine.model})
        </p>
      )}
      {part && (
        <article
          className="cw-card"
          aria-label={ctx.recommended_part ? 'Recommended part' : 'Compatible part'}
        >
          <header>
            <h3>{part.name}</h3>
            <span className="cw-mono">{part.part_number}</span>
            {ctx.recommended_part ? (
              <Chip value="RECOMMEND">Recommended</Chip>
            ) : (
              <Chip value="NO_AVAILABLE_RECOMMENDATION">Not recommended: unavailable</Chip>
            )}
          </header>
          <dl className="cw-facts">
            <dt>Product match</dt>
            <dd>{label(part.product_match_status)}</dd>
            <dt>Fitment</dt>
            <dd>{label(part.fitment)}</dd>
            <dt>Approved source</dt>
            <dd>{part.approved_source ? 'Yes' : 'No'}</dd>
            <dt>Availability</dt>
            <dd>
              {label(avail?.state ?? part.availability)}
              {avail?.total_available != null ? ` · ${avail.total_available} units recorded` : ''}
            </dd>
            {money(part.price) && (
              <>
                <dt>Price</dt>
                <dd>{money(part.price)}</dd>
              </>
            )}
          </dl>
        </article>
      )}
      {ctx.alternatives.length > 0 && (
        <>
          <h4 className="cw-h">Alternatives that pass every check</h4>
          <ul className="cw-list">
            {ctx.alternatives.map((a) => (
              <li key={a.part_id}>
                <span className="cw-mono">{a.part_number}</span> {a.name}
              </li>
            ))}
          </ul>
        </>
      )}
      {ctx.ranking.length > 0 && (
        <>
          <h4 className="cw-h">Ranking</h4>
          <table className="cw-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Part</th>
                <th>Score</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {ctx.ranking.slice(0, 6).map((r) => (
                <tr key={r.part_id}>
                  <td>{r.rank}</td>
                  <td>
                    <span className="cw-mono">{r.part_number}</span>
                  </td>
                  <td>{r.total_score}</td>
                  <td>{(r.explanation?.lines ?? []).join(' · ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {rejected.length > 0 && (
        <>
          <h4 className="cw-h">Not offered, and why</h4>
          <ul className="cw-list">
            {rejected.slice(0, 10).map(([id, reasons]) => (
              <li key={id}>
                <span className="cw-mono">{nameOf(id)?.part_number ?? id}</span>{' '}
                {nameOf(id)?.name ?? ''} — <Chip value={reasons[0]?.code ?? ''} />{' '}
                {reasons[0]?.detail}
              </li>
            ))}
          </ul>
        </>
      )}
      {!bare && ctx.clarification && (
        <>
          <h4 className="cw-h">{ctx.clarification.question}</h4>
          <Options options={ctx.clarification.options} onPick={onPick} />
        </>
      )}
    </section>
  )
}

// ── one part: which machines use it, where it came from ──────────────────────────────────────────
export function LookupView({ ctx }: { ctx: PartLookupContext }) {
  const cat = ctx.catalogue
  return (
    <section
      className="cw-view"
      aria-label={
        ctx.lookup === 'PART_FITMENT'
          ? 'Machines this part is approved for'
          : ctx.lookup === 'PART_STOCK'
            ? 'Recorded stock of this part'
            : 'Recorded origin of this part'
      }
    >
      {ctx.part && (
        <p className="cw-meta">
          <span className="cw-mono">{ctx.part.part_number}</span> {ctx.part.name}
        </p>
      )}
      {ctx.lookup === 'PART_STOCK' ? (
        <>
          <dl className="cw-facts">
            <dt>Stock</dt>
            <dd>
              {label(ctx.stock?.state)}
              {ctx.stock?.total_available != null
                ? ` · ${ctx.stock.total_available} units recorded`
                : ''}
            </dd>
          </dl>
          {ctx.stock?.depots?.length ? (
            <table className="cw-table" aria-label="Stock by depot">
              <thead>
                <tr>
                  <th>Depot</th>
                  <th>Status</th>
                  <th>Available</th>
                </tr>
              </thead>
              <tbody>
                {ctx.stock.depots.map((d) => (
                  <tr key={d.location_id}>
                    <td className="cw-mono">{d.location_id}</td>
                    <td>{label(d.status)}</td>
                    <td>{d.available_quantity ?? 'not recorded'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          <p className="cw-meta">
            Stock does not establish that the part fits a machine. Add the machine model to check
            fitment.
          </p>
        </>
      ) : ctx.lookup === 'PART_FITMENT' ? (
        <>
          {ctx.machines.length > 0 ? (
            <table className="cw-table" aria-label="Approved machines">
              <thead>
                <tr>
                  <th>Machine</th>
                  <th>Model</th>
                  <th>Fitment</th>
                </tr>
              </thead>
              <tbody>
                {ctx.machines.map((m) => (
                  <tr key={m.fitment_id}>
                    <td>{m.name}</td>
                    <td className="cw-mono">{m.model}</td>
                    <td>{label(m.fitment_rule)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="cw-meta">No fitment record approves this part for a machine model.</p>
          )}
          {ctx.other_fitments.length > 0 && (
            <p className="cw-meta">
              Other fitment records, not approved:{' '}
              {ctx.other_fitments.map((m) => `${m.model} (${label(m.approval_status)})`).join(', ')}
              .
            </p>
          )}
        </>
      ) : (
        <>
          {cat && (
            <dl className="cw-facts">
              <dt>Manufacturer</dt>
              <dd>{cat.manufacturer ?? 'not recorded'}</dd>
              <dt>OEM status</dt>
              <dd>{label(cat.oem_status)}</dd>
              <dt>Catalogue record</dt>
              <dd>
                {label(cat.catalogue_status)} · {label(cat.data_status)}
              </dd>
            </dl>
          )}
          {ctx.sources.length > 0 ? (
            <ul className="cw-list">
              {ctx.sources.map((s) => (
                <li key={s.approved_source_id}>
                  Approved {label(s.source_kind)} source{' '}
                  <span className="cw-mono">{s.source_id}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="cw-meta">No approved source is recorded for this part.</p>
          )}
        </>
      )}
    </section>
  )
}

// ── logistics ────────────────────────────────────────────────────────────────────────────────────
/** The recorded routes to a place with no shipment: potential, fastest first, each with its own days and cost. */
export function RouteOptionsView({ ctx }: { ctx: RouteOptionsContext }) {
  return (
    <section className="cw-view" aria-label="Recorded routes to the destination">
      {ctx.destinations.map((d) => (
        <div key={d.location_id}>
          <h4 className="cw-h">
            {d.city ?? d.name} <span className="cw-meta">{d.country}</span>
          </h4>
          <table className="cw-table" aria-label={`Routes to ${d.city ?? d.name}`}>
            <thead>
              <tr>
                <th>Route</th>
                <th>Mode</th>
                <th>Transit</th>
                <th>Cost</th>
                <th>From</th>
              </tr>
            </thead>
            <tbody>
              {d.routes.map((r) => (
                <tr key={r.route_id}>
                  <td className="cw-mono">{r.route_id}</td>
                  <td>
                    {label(r.transport_mode)}
                    {r.service_level ? ` · ${label(r.service_level)}` : ''}
                  </td>
                  <td>{days(r.planned_transit_days)}</td>
                  <td>
                    {r.estimated_cost != null
                      ? `${r.estimated_cost} ${r.currency ?? ''}`.trim()
                      : 'not recorded'}
                  </td>
                  <td>{r.origin.name ?? r.origin.location_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <p className="cw-note">
        Potential routes on the network: none is assigned to a shipment, and the days and cost are
        the route records' own demonstration values, not a booking or a delivery date.
      </p>
    </section>
  )
}

export function LogisticsView({
  ctx,
  onPick,
  bare,
}: {
  ctx: LogisticsContext
  onPick?: (o: Record<string, unknown>) => void
  bare?: boolean
}) {
  const s = ctx.shipment
  const total = ctx.route_legs.length
  const done = ctx.completed_legs.length
  const alternatives = (ctx.transport_comparison?.options ?? []).filter((o) => !o.is_current)
  return (
    <section className="cw-view" aria-label="Shipment result">
      {!bare && <Banner ctx={ctx} />}
      {!s && ctx.order && (
        <>
          <dl className="cw-facts">
            <dt>Order</dt>
            <dd className="cw-mono">{ctx.order.order_id}</dd>
            <dt>Status</dt>
            <dd>{label(ctx.order.status)}</dd>
            {ctx.order.order_date && (
              <>
                <dt>Placed</dt>
                <dd>{ctx.order.order_date}</dd>
              </>
            )}
            <dt>Shipment</dt>
            <dd>none recorded yet</dd>
          </dl>
          {ctx.order_lines.length > 0 && (
            <table className="cw-table" aria-label="Order lines">
              <thead>
                <tr>
                  <th>Order line</th>
                  <th>Part</th>
                  <th>Qty</th>
                </tr>
              </thead>
              <tbody>
                {ctx.order_lines.map((l) => (
                  <tr key={l.order_line_id}>
                    <td className="cw-mono">{l.order_line_id}</td>
                    <td>
                      <span className="cw-mono">{l.part_number ?? 'not recorded'}</span>{' '}
                      {l.name ?? ''}
                    </td>
                    <td>{l.quantity ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {s && (
        <dl className="cw-facts">
          <dt>Shipment</dt>
          <dd className="cw-mono">{s.shipment_id}</dd>
          <dt>Order</dt>
          <dd className="cw-mono">{s.order_id ?? 'not recorded'}</dd>
          <dt>Status</dt>
          <dd>{label(ctx.current_status ?? s.status)}</dd>
          {s.carrier && (
            <>
              <dt>Carrier</dt>
              <dd>{s.carrier}</dd>
            </>
          )}
          {ctx.planned_eta?.planned_eta && (
            <>
              <dt>{ctx.planned_eta.delivered ? 'Delivered' : 'Planned ETA'}</dt>
              <dd>
                {ctx.planned_eta.actual_eta ?? ctx.planned_eta.planned_eta}
                {ctx.planned_eta.days_to_eta != null && !ctx.planned_eta.delivered
                  ? ` · ${days(ctx.planned_eta.days_to_eta)} ${ctx.planned_eta.days_to_eta < 0 ? 'ago' : 'to go'}`
                  : ''}
              </dd>
            </>
          )}
        </dl>
      )}
      {s && (
        <>
          <h4 className="cw-h">
            What is in this shipment{' '}
            <Chip value={ctx.shipment_kind === 'MULTI_LINE' ? 'UNKNOWN' : 'PASS'}>
              {ctx.shipment_kind === 'MULTI_LINE'
                ? `${ctx.shipment_lines.length} order lines`
                : ctx.shipment_kind === 'SINGLE_LINE'
                  ? 'one order line'
                  : 'no line recorded'}
            </Chip>
          </h4>
          {ctx.shipment_lines.length > 0 ? (
            <table className="cw-table" aria-label="Order lines in this shipment">
              <thead>
                <tr>
                  <th>Order line</th>
                  <th>Part</th>
                  <th>Qty</th>
                </tr>
              </thead>
              <tbody>
                {ctx.shipment_lines.map((l) => (
                  <tr key={l.order_line_id}>
                    <td className="cw-mono">{l.order_line_id}</td>
                    <td>
                      <span className="cw-mono">{l.part_number ?? 'not recorded'}</span>{' '}
                      {l.name ?? ''}
                    </td>
                    <td>{l.quantity ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="cw-meta">No order line is recorded for this shipment.</p>
          )}
        </>
      )}
      {ctx.order_split && (
        <p className="cw-note" role="note">
          This order was split into {ctx.order_shipments.length} separate shipments:{' '}
          {ctx.order_shipments
            .map((id) => (id === s?.shipment_id ? `${id} (this one)` : id))
            .join(', ')}
          .
        </p>
      )}
      {ctx.route && total > 0 && (
        <>
          <h4 className="cw-h">
            Route {ctx.route.route_id} · {label(ctx.route.transport_mode)}
          </h4>
          <div
            className="cw-progress"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={done}
            aria-label={`${done} of ${total} legs completed`}
          >
            {ctx.route_legs.map((leg) => (
              <span
                key={leg.sequence}
                className={leg.sequence <= done ? 'is-done' : ''}
                title={`${label(leg.transport_mode)} · ${days(leg.planned_transit_days)}`}
              />
            ))}
          </div>
          <p className="cw-meta">
            {done} of {total} legs completed
            {ctx.remaining_legs.length
              ? `; remaining: ${ctx.remaining_legs.map((l) => `${label(l.transport_mode)} ${days(l.planned_transit_days)}`).join(', ')}`
              : ''}
            .
          </p>
        </>
      )}
      {alternatives.length > 0 && (
        <>
          <h4 className="cw-h">Recorded alternatives for this lane</h4>
          <table className="cw-table">
            <thead>
              <tr>
                <th>Route</th>
                <th>Mode</th>
                <th>Days</th>
                <th>Versus now</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {alternatives.map((o) => (
                <tr key={o.route_id}>
                  <td className="cw-mono">{o.route_id}</td>
                  <td>{label(o.transport_mode)}</td>
                  <td>{o.planned_transit_days ?? '—'}</td>
                  <td>
                    {o.days_vs_current == null
                      ? '—'
                      : o.days_vs_current === 0
                        ? 'same'
                        : `${days(o.days_vs_current)} ${o.days_vs_current < 0 ? 'faster' : 'slower'}`}
                  </td>
                  <td>
                    {o.estimated_cost ?? '—'} {o.currency ?? ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {ctx.tracking_events.length > 0 && (
        <>
          <h4 className="cw-h">Tracking</h4>
          <ol className="cw-timeline">
            {ctx.tracking_events.map((e) => (
              <li key={e.tracking_event_id}>
                <time>{e.timestamp.slice(0, 16).replace('T', ' ')}</time> {label(e.event_type)}
                {e.location_text ? ` · ${e.location_text}` : ''}
              </li>
            ))}
          </ol>
        </>
      )}
      {!bare && ctx.clarification && (
        <>
          <h4 className="cw-h">{ctx.clarification.question}</h4>
          <Options options={ctx.clarification.options} onPick={onPick} />
        </>
      )}
    </section>
  )
}

// ── warranty ─────────────────────────────────────────────────────────────────────────────────────
export function WarrantyView({
  ctx,
  onPick,
  bare,
}: {
  ctx: WarrantyContext
  onPick?: (o: Record<string, unknown>) => void
  bare?: boolean
}) {
  const hidden = ctx.visibility?.hidden_fields ?? []
  const options = (ctx.decision.facts.options as Record<string, unknown>[] | undefined) ?? []
  return (
    <section className="cw-view" aria-label="Warranty result">
      {!bare && <Banner ctx={ctx} />}
      {ctx.coverage_start && (
        <p className="cw-meta">
          Coverage {ctx.coverage_start} to {ctx.coverage_end}
        </p>
      )}
      {ctx.decision_factors.length > 0 && (
        <>
          <h4 className="cw-h">Checks</h4>
          <ul className="cw-checks">
            {ctx.decision_factors.map((f) => (
              <li key={f.code}>
                <Chip value={f.status} /> <strong>{f.label}</strong> <span>{f.detail}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {ctx.installation && (
        <>
          <h4 className="cw-h">Installation</h4>
          <dl className="cw-facts">
            <dt>Part</dt>
            <dd>
              {ctx.current_part
                ? `${ctx.current_part.name} (${ctx.current_part.part_number})`
                : 'not recorded'}
            </dd>
            <dt>Installed</dt>
            <dd>{ctx.installation.installation_date}</dd>
            <dt>Dealer</dt>
            <dd>
              {ctx.dealer
                ? `${ctx.dealer.name} · ${label(ctx.dealer.authorized_status)}`
                : 'not recorded'}
            </dd>
            <dt>Technician</dt>
            <dd>
              {ctx.technician
                ? [ctx.technician.name, ctx.technician.certification, ctx.technician.specialization]
                    .filter(Boolean)
                    .join(' · ') || ctx.technician.technician_id
                : 'not recorded'}
              {hidden.includes('technician.name') ? ' (name not shown to your role)' : ''}
            </dd>
            <dt>Work order</dt>
            <dd>
              {ctx.work_order
                ? `${ctx.work_order.work_order_id} · ${label(ctx.work_order.service_type)} · ${ctx.work_order.service_date ?? ''}`
                : 'none recorded'}
            </dd>
            <dt>Installation record</dt>
            <dd>
              {label(ctx.installation.validation_status)}
              {ctx.installation.validation_issues?.length
                ? ` (${ctx.installation.validation_issues.map(label).join(', ')})`
                : ''}
            </dd>
          </dl>
        </>
      )}
      {ctx.machine && (
        <>
          <h4 className="cw-h">Replacement history</h4>
          {ctx.replacement_history.length ? (
            <ul className="cw-list">
              {ctx.replacement_history.map((r) => (
                <li key={r.replacement_id}>
                  <span className="cw-mono">{r.replacement_id}</span> {r.replacement_date}
                  {r.reason ? ` · ${r.reason}` : ''}
                </li>
              ))}
            </ul>
          ) : (
            <p className="cw-meta">No replacement of this part is recorded.</p>
          )}
          {ctx.prior_claims.length > 0 && (
            <p className="cw-meta">
              Earlier claims:{' '}
              {ctx.prior_claims.map((c) => `${c.claim_id} (${label(c.status)})`).join(', ')}
            </p>
          )}
        </>
      )}
      {!bare && options.length > 0 && (
        <>
          <h4 className="cw-h">Which one do you mean?</h4>
          <Options options={options} onPick={onPick} />
        </>
      )}
    </section>
  )
}

// ── evidence and provenance ──────────────────────────────────────────────────────────────────────
function Path({ steps }: { steps: PathStep[] }) {
  if (!steps.length) return null
  return (
    <ol className="cw-path" aria-label="Evidence path">
      {steps.map((s) => (
        <li key={s.step}>
          <span className="cw-path__entity">{s.entity}</span>{' '}
          <span className="cw-mono">{s.id ?? ''}</span>
          {s.relation_to_next && <span className="cw-path__rel"> —{s.relation_to_next}→</span>}
        </li>
      ))}
    </ol>
  )
}

export interface EvidenceBundle {
  evidence: EvidenceItem[]
  evidence_paths: AgentResponse['evidence_paths']
  source_records: DataRef[]
  confidence: AgentResponse['confidence']
  visibility: AgentResponse['visibility']
  data_status: string
  synthetic_notice: string | null
  warnings: string[]
  missing: string[]
}

export function bundleFrom(
  contexts: AgentResponse['contexts'],
  notice: string | null,
): EvidenceBundle {
  const entries = (Object.entries(contexts) as [Domain, CommerceContext][]).filter(([, c]) => c)
  const seen = new Set<string>()
  const records: DataRef[] = []
  for (const [, c] of entries)
    for (const r of c.source_records) {
      const k = `${r.entity}|${r.id}`
      if (!seen.has(k)) {
        seen.add(k)
        records.push(r)
      }
    }
  const statuses = [...new Set(records.map((r) => r.data_status).filter(Boolean))]
  return {
    evidence: entries.flatMap(([d, c]) => c.evidence.map((e) => ({ ...e, domain: d }))),
    evidence_paths: Object.fromEntries(entries.map(([d, c]) => [d, c.evidence_path])),
    source_records: records,
    confidence: Object.fromEntries(entries.map(([d, c]) => [d, c.confidence])) as Partial<
      Record<Domain, Confidence>
    >,
    visibility: Object.fromEntries(entries.map(([d, c]) => [d, c.visibility])),
    data_status: statuses.length === 1 ? String(statuses[0]) : statuses.length ? 'MIXED' : 'NONE',
    synthetic_notice:
      notice ??
      (statuses.includes('SYNTHETIC_DEMO')
        ? 'This is demonstration data: the records are synthetic demo data, not real operational data.'
        : null),
    warnings: [...new Set(entries.flatMap(([, c]) => c.warnings))],
    missing: [...new Set(entries.flatMap(([, c]) => c.missing))],
  }
}

export function EvidenceView({ bundle }: { bundle: EvidenceBundle | null }) {
  if (
    !bundle ||
    (!bundle.evidence.length &&
      !bundle.source_records.length &&
      !Object.keys(bundle.evidence_paths).length)
  ) {
    return (
      <p className="cw-empty">
        Ask the assistant something, or open a part, shipment or claim: the evidence behind the
        answer appears here.
      </p>
    )
  }
  const domains = Object.keys(bundle.evidence_paths) as Domain[]
  return (
    <section className="cw-view" aria-label="Evidence and provenance">
      {bundle.synthetic_notice && (
        <p className="cw-note" role="note">
          {bundle.synthetic_notice}
        </p>
      )}
      {domains.map((d) => (
        <div key={d} className="cw-evidence">
          <h4 className="cw-h">{label(d)}</h4>
          <Path steps={bundle.evidence_paths[d] ?? []} />
          {bundle.confidence[d] && (
            <p className="cw-meta">
              {label(bundle.confidence[d]?.level)} · data {label(bundle.confidence[d]?.data_status)}{' '}
              · facts{' '}
              {bundle.confidence[d]?.fact_verified ? 'checked against the records' : 'not verified'}{' '}
              ·{' '}
              {bundle.confidence[d]?.real_world_verified
                ? 'real-world verified'
                : 'not real-world verified'}
            </p>
          )}
          {(bundle.visibility[d]?.hidden_fields.length ?? 0) > 0 && (
            <p className="cw-meta">
              Hidden for the {label(bundle.visibility[d]?.role)} view:{' '}
              {bundle.visibility[d]?.hidden_fields.join(', ')}.
            </p>
          )}
        </div>
      ))}
      {bundle.evidence.length > 0 && (
        <>
          <h4 className="cw-h">Evidence</h4>
          <ul className="cw-list">
            {bundle.evidence.map((e, i) => (
              <li key={i}>
                {e.fact}{' '}
                <span className="cw-meta">
                  ({e.entity} {e.id ?? ''}
                  {e.data_status ? ` · ${label(e.data_status)}` : ''})
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {bundle.warnings.length > 0 && (
        <>
          <h4 className="cw-h">Warnings</h4>
          <ul className="cw-list">
            {bundle.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </>
      )}
      {bundle.missing.length > 0 && (
        <p className="cw-meta">Not available: {bundle.missing.join(', ')}.</p>
      )}
      <details className="cw-records">
        <summary>
          {bundle.source_records.length} source records · data {label(bundle.data_status)}
        </summary>
        <table className="cw-table">
          <thead>
            <tr>
              <th>Entity</th>
              <th>Id</th>
              <th>Data</th>
            </tr>
          </thead>
          <tbody>
            {bundle.source_records.map((r) => (
              <tr key={`${r.entity}|${r.id}`}>
                <td>{r.entity}</td>
                <td className="cw-mono">{r.id}</td>
                <td>{label(r.data_status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  )
}
