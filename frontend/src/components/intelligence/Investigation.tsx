import { getPartFitment, getPartInventory, getPartProvenance, getPartSuppliers, type PartOverview, type PartTab } from '../../api'
import { useApi } from '../../hooks/useApi'
import { humanize } from '../../lib/format'
import { DATA_CLASS_LABEL } from './provenance'

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
const isConfirmed = (status: string | null) => status?.toUpperCase() === 'CONFIRMED'

/** The business relationships the diagram explains, in reading order. Technical edges (aliases, specs, price records) stay in the graph tab. */
const EXPLAINED = ['SUPPLIED_BY', 'STOCKED_BY', 'AVAILABLE_AT', 'PART_OF', 'HAS_COMPLIANCE', 'RELATED_COMPONENT', 'CO_ORDERED_WITH']

/**
 * The investigation summary of one part, read as a document: fitment, supply, how it is connected, and why each of those
 * statements can be trusted. Every line comes from the part's own endpoints; nothing missing is filled in.
 */
export function Investigation({ overview, onTab }: { overview: PartOverview; onTab: (tab: PartTab) => void }) {
  const key = overview.part_number
  const fitment = useApi((s) => getPartFitment(key, s), `fitment:${key}`)
  const suppliers = useApi((s) => getPartSuppliers(key, s), `suppliers:${key}`)
  const inventory = useApi((s) => getPartInventory(key, s), `inventory:${key}`)
  const provenance = useApi((s) => getPartProvenance(key, s), `provenance:${key}`)

  const fits = fitment.data ?? []
  const confirmed = fits.filter((f) => isConfirmed(f.fitment_status))
  const sup = suppliers.data ?? []
  const primary = sup.find((s) => s.is_primary) ?? sup[0]
  const inv = inventory.data
  const stocked = (inv?.warehouses ?? []).filter((w) => (w.available ?? 0) > 0)
  const prov = provenance.data
  const connected = (prov?.relationship_sources ?? []).filter((r) => r.relationship !== 'FITS' && r.count > 0)
  const branches = EXPLAINED.flatMap((rel) => connected.filter((r) => r.relationship === rel))
  const others = connected.length - branches.length

  const machine = confirmed[0] ?? fits[0]
  const why: { ok: boolean; title: string; detail: string; data: string }[] = [
    {
      ok: confirmed.length > 0,
      title: 'Fitment',
      detail: confirmed.length ? `Confirmed for ${plural(confirmed.length, 'machine')} · catalogue evidence` : fits.length ? 'Only conditional fitment is recorded' : 'No fitment evidence',
      data: fits[0] ? DATA_CLASS_LABEL[fits[0].data_class] : 'Not connected',
    },
    {
      ok: stocked.length > 0,
      title: 'Availability',
      detail: inv ? `${inv.availability_label ?? 'Not connected'}${inv.total_available != null ? ` · ${inv.total_available} units in ${plural(stocked.length, 'warehouse')}` : ''} · inventory evidence` : 'Reading inventory…',
      data: inv ? DATA_CLASS_LABEL[inv.data_class] : '—',
    },
    {
      ok: sup.length > 0,
      title: 'Supplier',
      detail: sup.length ? `${plural(sup.length, 'supplier relationship')} · supplier evidence` : 'No supplier relationship recorded',
      data: primary ? DATA_CLASS_LABEL[primary.data_class] : 'Not connected',
    },
    {
      ok: true,
      title: 'Provenance',
      detail: prov ? [prov.source_name ?? prov.source_file, prov.verification].filter(Boolean).join(' · ') : 'Reading provenance…',
      data: prov ? DATA_CLASS_LABEL[prov.classification] : '—',
    },
  ]

  return (
    <div className="inv">
      <div className="grid grid-2">
        <section className="card card-pad" aria-labelledby="inv-fit">
          <div className="spread inv__head">
            <h3 id="inv-fit">Machine & fitment</h3>
            <button type="button" className="link-btn" onClick={() => onTab('fitment')}>
              Fitment detail
            </button>
          </div>
          {fitment.data === null && !fitment.error ? (
            <p className="pw-loading">Reading fitment…</p>
          ) : fits.length === 0 ? (
            <p className="pi-empty">No machine fitment is recorded for this part.</p>
          ) : (
            <ul className="kv-list">
              {fits.map((f) => (
                <li key={f.model_code} className="kv-row">
                  <span>
                    <strong className="inv__model">{f.model_code}</strong> {f.name ?? f.machine_type ?? ''}
                  </span>
                  <span>
                    <span className={`tag ${isConfirmed(f.fitment_status) ? 'tag-good' : 'tag-warn'}`}>
                      {isConfirmed(f.fitment_status) ? 'Confirmed fit' : f.fitment_status ? humanize(f.fitment_status) : 'Status not stated'}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card card-pad" aria-labelledby="inv-supply">
          <div className="spread inv__head">
            <h3 id="inv-supply">Supply</h3>
            <button type="button" className="link-btn" onClick={() => onTab('suppliers')}>
              Supplier detail
            </button>
          </div>
          <dl className="kv-list">
            <div className="kv-row">
              <dt>Supplier</dt>
              <dd>
                {primary ? primary.name ?? primary.supplier_id : 'No supplier relationship recorded'}
                {primary ? <small>{[primary.is_primary ? 'Primary' : null, primary.lead_time_days != null ? `lead time ${primary.lead_time_days} days` : null, sup.length > 1 ? `${plural(sup.length, 'supplier')} in total` : null].filter(Boolean).join(' · ')}</small> : null}
              </dd>
            </div>
            <div className="kv-row">
              <dt>Warehouse</dt>
              <dd>
                {stocked.length ? stocked.map((w) => w.name ?? w.warehouse_id).join(', ') : inv?.state === 'NOT_CONNECTED' ? 'Not connected' : 'No warehouse holds stock'}
                {stocked.length ? <small>{plural(stocked.length, 'warehouse')} with stock</small> : null}
              </dd>
            </div>
            <div className="kv-row">
              <dt>Availability</dt>
              <dd>
                {inv?.availability_label ?? (inv ? 'Not connected' : '—')}
                {inv?.total_available != null ? <small>{inv.total_available} units recorded</small> : null}
              </dd>
            </div>
          </dl>
        </section>

        <section className="card card-pad" aria-labelledby="inv-rel">
          <div className="spread inv__head">
            <h3 id="inv-rel">Relationships</h3>
            <button type="button" className="link-btn" onClick={() => onTab('graph')}>
              Open graph
            </button>
          </div>
          <p className="pi-diagram" aria-label="How this part is connected in the graph">
            {machine ? (
              <>
                <span>{machine.model_code}</span>
                <span className="arrow">→ fits →</span>
              </>
            ) : null}
            <span className="is-part">{overview.part_number}</span>
          </p>
          {branches.length ? (
            <ul className="kv-list">
              {branches.map((b) => (
                <li key={b.relationship} className="kv-row">
                  <span>
                    <span className="rel-type">{b.relationship}</span>
                  </span>
                  <span>
                    {b.count} · {b.connected_label}
                  </span>
                </li>
              ))}
            </ul>
          ) : prov ? (
            <p className="pi-empty">No supply, stock or assembly relationships are recorded.</p>
          ) : null}
          {others > 0 ? <p className="small muted inv__more">and {plural(others, 'further relationship type')} in the graph</p> : null}
        </section>

        <section className="card card-pad" aria-labelledby="inv-why">
          <div className="spread inv__head">
            <h3 id="inv-why">Why this result</h3>
            <button type="button" className="link-btn" onClick={() => onTab('provenance')}>
              Full provenance
            </button>
          </div>
          <ul className="evidence-list">
            {why.map((w) => (
              <li key={w.title} className={`ev-item ${w.ok ? 'is-ok' : 'is-warn'}`}>
                <span className="ev-mark" aria-hidden="true">
                  {w.ok ? '✓' : '!'}
                </span>
                <div>
                  <p className="ev-title">
                    {w.title} <span className="badge badge-data">{w.data}</span>
                  </p>
                  <p className="ev-detail">{w.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
