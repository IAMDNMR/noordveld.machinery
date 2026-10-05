import { Check, ShoppingCart } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getPart, type PartDetail, type RelationKind } from '../api'
import { AvailabilityBadge, canOrder, DemoTag, StatusFlag } from '../components/store/Badges'
import { PartImage } from '../components/store/PartImage'
import { QtyStepper } from '../components/store/QtyStepper'
import { ErrorView } from '../components/store/StateViews'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../hooks/usePageMeta'
import { formatMoney, humanize, NOT_AVAILABLE } from '../lib/format'
import { codeLabel, statusLabel } from '../lib/partStatus'
import { categoryPath, machinePath, partPath, STORE_ROUTE } from '../lib/storeQuery'
import { useCart } from '../store/CartContext'

const NOT_CONFIGURED = 'Not configured'

/** What each graph relationship means. None of them says the parts are interchangeable. */
const RELATION: Record<RelationKind, string> = {
  SAME_NAME_GROUP_AS: 'Shares a part name',
  RELATED_COMPONENT: 'Related component',
  CO_ORDERED_WITH: 'Often ordered together',
}

const Section = ({ id, title, children, note }: { id: string; title: string; children: ReactNode; note?: string }) => (
  <section className="pd-section card card-pad" aria-labelledby={`${id}-title`} id={id}>
    <h3 id={`${id}-title`}>{title}</h3>
    {note ? <p className="small muted pd-section__note">{note}</p> : null}
    {children}
  </section>
)

const Facts = ({ rows }: { rows: [string, ReactNode][] }) => (
  <dl className="kv-list">
    {rows.map(([label, value], i) => (
      <div className="kv-row" key={`${i}-${label}`}>
        <dt>{label}</dt>
        <dd>{value}</dd>
      </div>
    ))}
  </dl>
)

const place = (city: string | null, country: string | null) => [city, country].filter(Boolean).join(', ')

export default function PartDetailPage() {
  const { partNo = '' } = useParams()
  const detail = useApi((signal) => getPart(partNo, signal), partNo)

  usePageMeta({
    title: detail.data ? `${detail.data.part.name} (${detail.data.part.part_number})` : 'Part',
    description: detail.data ? `${detail.data.part.name}, Noordveld part ${detail.data.part.part_number}: compatible machines, specifications and legacy references.` : 'Noordveld part details.',
    path: `${STORE_ROUTE}/${partNo}`,
  })

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [partNo])

  if (detail.error?.notFound)
    return (
      <div className="wf-container pd-missing">
        <h1>Part not found</h1>
        <p className="muted">No part “{partNo}” exists in the Noordveld catalogue.</p>
        <Link to={STORE_ROUTE} className="btn btn-primary">
          Back to the Parts Store
        </Link>
      </div>
    )
  if (detail.error)
    return (
      <div className="wf-container pd-missing">
        <ErrorView error={detail.error} onRetry={detail.reload} what="This part" />
      </div>
    )
  if (!detail.data)
    return (
      <div className="wf-container pd-missing" role="status">
        <p className="muted">Loading part…</p>
      </div>
    )
  return <PartView d={detail.data} />
}

function PartView({ d }: { d: PartDetail }) {
  const { part, profile, price } = d
  const { add, lines, setOpen } = useCart()
  const [qty, setQty] = useState(1)
  const [added, setAdded] = useState(false)
  // the machine this part is bought for: it travels with the cart line and the order. Chosen by the user; preselected only when the catalogue records a single fit.
  const [machine, setMachine] = useState<string>(() => (d.fitment.length === 1 ? d.fitment[0].model_code : ''))
  const inCart = lines.filter((l) => l.partId === part.part_id).reduce((n, l) => n + l.qty, 0)
  const orderable = canOrder(profile?.part_status, profile?.orderable) ? true : profile?.orderable === true ? false : profile?.orderable
  const totalStock = d.warehouses.length > 0 ? d.warehouses.reduce((n, w) => n + (w.available ?? 0), 0) : null
  const attention = d.identification.filter((i) => i.identification_needed)
  const specGroups = [...new Set(d.specifications.map((s) => s.group ?? ''))]
  const primary = d.suppliers.find((s) => s.is_primary) ?? d.suppliers[0]

  const addToCart = () => {
    add(part.part_id, qty, machine || null)
    setAdded(true)
    window.setTimeout(() => setAdded(false), 1800)
  }

  return (
    <article className="wf-container pd-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link to={STORE_ROUTE}>Parts Store</Link>
        {part.category ? (
          <>
            <span className="crumb-sep">/</span>
            <Link to={categoryPath(part.category)}>{part.category}</Link>
          </>
        ) : null}
        <span className="crumb-sep">/</span>
        <span className="crumb-current" aria-current="page">
          {part.part_number}
        </span>
      </nav>

      <div className="pd-head">
        <div className="pd-visual">
          <PartImage partNumber={part.part_number} category={part.category} name={part.name} variant="large" />
        </div>

        <div className="pd-info">
          <p className="part-number">{part.part_number}</p>
          <h1>{part.name}</h1>
          {part.note ? <p className="muted pd-desc">{part.note}</p> : null}
          <div className="row pd-tags">
            <AvailabilityBadge availability={profile ? { state: profile.availability_state, orderable: profile.orderable, part_status: profile.part_status, total_available: totalStock, data_status: profile.data_status } : null} />
            {profile?.part_status === 'VERIFIED' ? <span className="tag tag-good">Verified</span> : null}
            <StatusFlag status={profile?.part_status} partNumber={part.part_number} />
            {d.legacy_references.length > 0 ? (
              <a className="link-more" href="#legacy">
                {d.legacy_references.length} legacy {d.legacy_references.length === 1 ? 'reference' : 'references'}
              </a>
            ) : null}
          </div>
          <p className="pd-price">
            {price ? (
              <>
                {formatMoney(price)} <span className="small muted">ex VAT</span> <DemoTag status={price.data_status} />
              </>
            ) : (
              <span className="muted">Price not available</span>
            )}
          </p>

          <div className="pd-stat-row">
            <div className="pd-stat card">
              <p className="label">Category</p>
              <p className="value">{part.subcategory ?? part.category ?? NOT_AVAILABLE}</p>
            </div>
            <div className="pd-stat card">
              <p className="label">Fits</p>
              <p className="value">{d.fitment.length ? `${d.fitment.length} ${d.fitment.length === 1 ? 'machine' : 'machines'}` : 'None recorded'}</p>
            </div>
            <div className="pd-stat card">
              <p className="label">In stock</p>
              <p className="value">{totalStock !== null ? `${totalStock} units` : NOT_CONFIGURED}</p>
            </div>
            <div className="pd-stat card">
              <p className="label">Lead time</p>
              <p className="value">{primary?.lead_time_days != null ? `${primary.lead_time_days} days` : NOT_AVAILABLE}</p>
            </div>
          </div>

          {attention.length > 0 ? (
            <div className="sim-banner pd-attention" role="note">
              Confirm before ordering:{' '}
              {attention.map((i) => [i.model_code, statusLabel(i.reason), codeLabel(i.identification_needed)].filter(Boolean).join(' · ')).join('; ')}
            </div>
          ) : null}

          <div className="pd-actions">
            {orderable === true ? (
              <>
                {d.fitment.length > 0 ? (
                  <label className="pd-machine">
                    <span>For machine</span>
                    <select value={machine} onChange={(e) => setMachine(e.target.value)} aria-label="Machine this part is for">
                      <option value="">Not specified</option>
                      {d.fitment.map((f) => (
                        <option key={f.machine_id} value={f.model_code}>
                          {f.name?.startsWith(f.model_code) ? f.name : `${f.model_code} ${f.name ?? ''}`.trim()} · {f.fitment_status === 'CONFIRMED' ? 'confirmed fit' : 'conditional fit'}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                <QtyStepper value={qty} onChange={setQty} label="Quantity" />
                <button type="button" className={`btn btn-primary ${added ? 'is-added' : ''}`} onClick={addToCart}>
                  {added ? <Check size={16} strokeWidth={2.2} aria-hidden="true" /> : <ShoppingCart size={16} strokeWidth={1.8} aria-hidden="true" />}
                  {added ? 'Added to cart' : 'Add to cart'}
                </button>
              </>
            ) : (
              <p className="small muted">{orderable === false ? 'This part cannot be ordered online.' : 'Online ordering is not configured for this part.'}</p>
            )}
            <Link className="btn btn-secondary" to={`/parts-intelligence?part=${encodeURIComponent(part.part_number)}`}>
              Investigate in Parts Intelligence
            </Link>
          </div>
          {inCart > 0 ? (
            <button type="button" className="link-more pd-incart" onClick={() => setOpen(true)}>
              {inCart} in your cart · View cart
            </button>
          ) : null}
        </div>
      </div>

      <div className="pd-sections">
        <div className="grid grid-2">
          <Section id="overview" title="Overview">
            <Facts
              rows={[
                ['Category', part.category ?? NOT_AVAILABLE],
                ['Subcategory', part.subcategory ?? NOT_AVAILABLE],
                ['Brand', part.brand ?? NOT_AVAILABLE],
                ['Plant of origin', part.origin_plant ?? NOT_AVAILABLE],
                ['Weight', profile?.weight_kg != null ? `${profile.weight_kg} kg` : NOT_AVAILABLE],
                ['Warranty', profile?.warranty_months != null ? `${profile.warranty_months} months` : NOT_AVAILABLE],
                ['Return window', profile?.return_window_days != null ? `${profile.return_window_days} days` : NOT_AVAILABLE],
                ...(profile?.status_reason ? ([['Catalogue status', `${profile.part_status ? humanize(profile.part_status) : ''} ${profile.status_reason}`.trim()]] as [string, ReactNode][]) : []),
              ]}
            />
          </Section>

          <Section id="machines" title="Fitment" note="Recorded per machine model. Conditional fitment depends on the stated condition.">
            {d.fitment.length === 0 ? (
              <p className="pi-empty">No fitment is recorded for this part.</p>
            ) : (
              <ul className="kv-list">
                {d.fitment.map((f) => {
                  const ident = d.identification.find((i) => i.model_code === f.model_code)
                  return (
                    <li key={f.machine_id} className="kv-row">
                      <span>
                        <Link className="link-more" to={machinePath(f.model_code)}>
                          {f.model_code}
                        </Link>{' '}
                        {f.name}
                        {f.condition_note ? <small>{f.condition_note}</small> : null}
                        {ident?.identification_needed ? <small className="fit-ident">{ident.reason ?? 'Machine identification needed'}</small> : null}
                      </span>
                      <span>
                        <span className={`tag ${f.fitment_status === 'CONFIRMED' ? 'tag-good' : 'tag-warn'}`}>{f.fitment_status === 'CONFIRMED' ? 'Confirmed fit' : f.fitment_status ? humanize(f.fitment_status) : 'Status not stated'}</span>
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}
          </Section>
        </div>

        <Section id="specifications" title="Specifications">
          {d.specifications.length === 0 ? (
            <p className="pi-empty">No specifications are recorded for this part.</p>
          ) : (
            <div className="kv-2col">
              {specGroups.map((group) => (
                <div key={group}>
                  {group ? <h4 className="pd-group">{group}</h4> : null}
                  <Facts rows={d.specifications.filter((s) => (s.group ?? '') === group).map((s) => [s.name, s.value ? `${s.value}${s.unit ? ` ${s.unit}` : ''}` : NOT_AVAILABLE])} />
                </div>
              ))}
            </div>
          )}
        </Section>

        <div className="grid grid-2">
          <Section id="supply" title="Supply" note="Supplier and dealer relationships are demonstration data.">
            <h4 className="pd-group">Suppliers</h4>
            {d.suppliers.length === 0 ? (
              <p className="small muted">{NOT_CONFIGURED}</p>
            ) : (
              <dl className="kv-list">
                {d.suppliers.map((s) => (
                  <div className="kv-row" key={s.supplier_id}>
                    <dt>
                      {s.name ?? s.supplier_id}
                      {s.is_primary ? ' · Primary' : ''}
                      <small>{place(s.city, s.country_code)}</small>
                    </dt>
                    <dd>{s.lead_time_days != null ? `${s.lead_time_days} days lead time` : 'Lead time not available'}</dd>
                  </div>
                ))}
              </dl>
            )}
            <h4 className="pd-group">Dealers</h4>
            {d.dealers.length === 0 ? (
              <p className="small muted">{NOT_CONFIGURED}</p>
            ) : (
              <dl className="kv-list">
                {d.dealers.map((x) => (
                  <div className="kv-row" key={x.dealer_id}>
                    <dt>
                      {x.name ?? x.dealer_id}
                      <small>{place(x.city, x.country_code)}</small>
                    </dt>
                    <dd>
                      {x.available != null ? `${x.available} available` : NOT_AVAILABLE}
                      {x.pickup_allowed ? <small>Collection possible</small> : null}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </Section>

          <Section id="availability" title="Availability" note="Stock values are demonstration data.">
            {d.warehouses.length === 0 ? (
              <p className="small muted">{NOT_CONFIGURED}</p>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Warehouse</th>
                      <th scope="col">Available</th>
                      <th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.warehouses.map((w) => (
                      <tr key={w.warehouse_id}>
                        <th scope="row">
                          {w.name ?? w.warehouse_id}
                          <small>{place(w.city, w.country_code)}</small>
                        </th>
                        <td>{w.available != null ? w.available : NOT_AVAILABLE}</td>
                        <td>{w.stock_status ? humanize(w.stock_status) : NOT_AVAILABLE}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="small muted pd-section__note">Delivery options and fulfilment: {NOT_CONFIGURED}.</p>
          </Section>
        </div>

        {d.compliance.length > 0 ? (
          <Section id="compliance" title="Compliance">
            <dl className="kv-list">
              {d.compliance.map((c, i) => (
                <div className="kv-row" key={i}>
                  <dt>{c.requirement ?? c.standard ?? c.certification}</dt>
                  <dd>
                    {c.standard ?? NOT_AVAILABLE}
                    <small>{[c.certificate_status ? humanize(c.certificate_status) : null, c.valid_until ? `valid until ${c.valid_until}` : null].filter(Boolean).join(' · ')}</small>
                  </dd>
                </div>
              ))}
            </dl>
          </Section>
        ) : null}

        {d.legacy_references.length > 0 ? (
          <Section id="legacy" title="Legacy references" note={`Numbers this part was known by before the unified Noordveld number ${part.part_number}. They are references, not alternatives.`}>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Legacy number</th>
                    <th scope="col">Legacy business</th>
                    <th scope="col">Mapping</th>
                  </tr>
                </thead>
                <tbody>
                  {d.legacy_references.map((l, i) => (
                    <tr key={`${l.legacy_part_number}-${i}`}>
                      <th scope="row">{l.legacy_part_number ?? NOT_AVAILABLE}</th>
                      <td>
                        {l.legacy_business ?? NOT_AVAILABLE}
                        <small>{l.legacy_plant}</small>
                      </td>
                      <td>
                        {l.mapping_type ? humanize(l.mapping_type) : NOT_AVAILABLE}
                        <small>{[l.mapping_confidence ? humanize(l.mapping_confidence) : null, l.note].filter(Boolean).join(' · ')}</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        ) : null}

        {d.related.length > 0 ? (
          <Section id="related" title="Related parts" note="Connected in the catalogue. Interchangeability is not established.">
            <div className="chip-row">
              {d.related.map((r) => (
                <Link key={`${r.part_id}-${r.relation}`} to={partPath(r.part_number)} className="chip">
                  <strong>{r.part_number}</strong> {r.name} <span className="muted">· {RELATION[r.relation]}</span>
                </Link>
              ))}
            </div>
          </Section>
        ) : null}

        <Section id="provenance" title="Provenance">
          <Facts
            rows={[
              ['Part record', part.data_status ? humanize(part.data_status) : NOT_AVAILABLE],
              ['Confidence', part.confidence ? humanize(part.confidence) : NOT_AVAILABLE],
              ['Source', [part.source_sheet, part.source_record_id].filter(Boolean).join(' · ') || NOT_AVAILABLE],
              ['Price, stock and supply', price?.data_status ? humanize(price.data_status) : NOT_AVAILABLE],
            ]}
          />
          <p className="small muted pd-section__note">Demonstration store: none of the data here is authoritative for ordering.</p>
        </Section>
      </div>
    </article>
  )
}
