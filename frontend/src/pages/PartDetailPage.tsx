import { Check, ChevronRight, ShoppingCart } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getPart, type PartDetail, type RelationKind } from '../api'
import { AvailabilityBadge, DemoTag, StatusFlag } from '../components/store/Badges'
import { PartImage } from '../components/store/PartImage'
import { QtyStepper } from '../components/store/QtyStepper'
import { ErrorView } from '../components/store/StateViews'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../hooks/usePageMeta'
import { formatMoney, humanize, NOT_AVAILABLE } from '../lib/format'
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
  <section className="pds" aria-labelledby={`${id}-title`} id={id}>
    <div className="container">
      <h2 id={`${id}-title`}>{title}</h2>
      {note ? <p className="pds__note">{note}</p> : null}
      {children}
    </div>
  </section>
)

const Facts = ({ rows }: { rows: [string, ReactNode][] }) => (
  <dl className="spec">
    {rows.map(([label, value], i) => (
      <div key={`${i}-${label}`}>
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

  useEffect(() => window.scrollTo(0, 0), [partNo])

  if (detail.error?.notFound)
    return (
      <div className="container pd-missing">
        <h1>Part not found</h1>
        <p>No part “{partNo}” exists in the Noordveld catalogue.</p>
        <Link to={STORE_ROUTE} className="button button--primary">
          Back to the Parts Store
        </Link>
      </div>
    )
  if (detail.error)
    return (
      <div className="container pd-missing">
        <ErrorView error={detail.error} onRetry={detail.reload} what="This part" />
      </div>
    )
  if (!detail.data)
    return (
      <div className="container pd-missing" role="status">
        <p>Loading part…</p>
      </div>
    )
  return <PartView d={detail.data} />
}

function PartView({ d }: { d: PartDetail }) {
  const { part, profile, price } = d
  const { add, lines, setOpen } = useCart()
  const [qty, setQty] = useState(1)
  const [added, setAdded] = useState(false)
  const inCart = lines.find((l) => l.partId === part.part_id)
  const orderable = profile?.orderable
  const totalStock = d.warehouses.length > 0 ? d.warehouses.reduce((n, w) => n + (w.available ?? 0), 0) : null
  const attention = d.identification.filter((i) => i.identification_needed)
  const specGroups = [...new Set(d.specifications.map((s) => s.group ?? ''))]

  const addToCart = () => {
    add(part.part_id, qty)
    setAdded(true)
    window.setTimeout(() => setAdded(false), 1800)
  }

  return (
    <article>
      <div className="pd container">
        <nav className="pd__crumbs" aria-label="Breadcrumb">
          <Link to={STORE_ROUTE}>Parts Store</Link>
          {part.category ? (
            <>
              <ChevronRight size={14} aria-hidden="true" />
              <Link to={categoryPath(part.category)}>{part.category}</Link>
            </>
          ) : null}
          <ChevronRight size={14} aria-hidden="true" />
          <span aria-current="page">{part.part_number}</span>
        </nav>

        <div className="pd__grid">
          <div className="pd__media">
            <PartImage partNumber={part.part_number} category={part.category} name={part.name} variant="large" />
          </div>

          <div className="pd__buy">
            <h1 className="pd__title">{part.name}</h1>
            <div className="pd__ids">
              <p className="pd__no">
                <span className="pd__no-label">Noordveld part number</span>
                <span className="mono">{part.part_number}</span>
              </p>
              {d.legacy_references.length > 0 ? (
                <a className="pd__legacy" href="#legacy">
                  {d.legacy_references.length} legacy {d.legacy_references.length === 1 ? 'reference' : 'references'}
                </a>
              ) : null}
            </div>
            {part.note ? <p className="pd__desc">{part.note}</p> : null}

            <div className="pd__price">
              {price ? (
                <>
                  <strong>{formatMoney(price)}</strong>
                  <span>ex VAT</span>
                  <small>
                    {price.price_status ? `${humanize(price.price_status)}. ` : ''}
                    {price.valid_from && price.valid_to ? `Valid ${price.valid_from} to ${price.valid_to}. ` : ''}
                    <DemoTag status={price.data_status} />
                  </small>
                </>
              ) : (
                <strong className="pd__price--none">Price not available</strong>
              )}
            </div>

            <div className="pd__stock">
              <AvailabilityBadge availability={profile ? { state: profile.availability_state, orderable: profile.orderable, part_status: profile.part_status, total_available: totalStock, data_status: profile.data_status } : null} />
              {totalStock !== null ? <span>{totalStock} units across {d.warehouses.length} warehouses</span> : null}
              <StatusFlag status={profile?.part_status} />
            </div>

            {attention.length > 0 ? (
              <div className="pd__notice" role="note">
                <div>
                  <h2>Confirm before ordering</h2>
                  {attention.map((i) => (
                    <p key={`${i.model_code}-${i.identification_needed}`}>
                      {i.model_code ? `${i.model_code}: ` : ''}
                      {i.reason ?? i.identification_needed}
                    </p>
                  ))}
                </div>
              </div>
            ) : null}

            {orderable === true ? (
              <>
                <div className="pd__order">
                  <QtyStepper value={qty} onChange={setQty} label="Quantity" />
                  <button type="button" className={`button button--primary pd__add ${added ? 'is-added' : ''}`} onClick={addToCart}>
                    {added ? <Check size={18} strokeWidth={2.2} aria-hidden="true" /> : <ShoppingCart size={18} strokeWidth={1.8} aria-hidden="true" />}
                    {added ? 'Added to cart' : 'Add to cart'}
                  </button>
                </div>
                {inCart ? (
                  <button type="button" className="pd__incart" onClick={() => setOpen(true)}>
                    {inCart.qty} in your cart · View cart
                  </button>
                ) : null}
              </>
            ) : (
              <p className="pd__desc">{orderable === false ? 'This part cannot be ordered online.' : 'Online ordering is not configured for this part.'}</p>
            )}
          </div>
        </div>
      </div>

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
        {d.assemblies.length > 0 ? (
          <>
            <h3 className="pds__sub">Used in</h3>
            <ul className="pds__list">
              {d.assemblies.map((a) => (
                <li key={a.assembly_id}>
                  <strong>{a.name ?? a.assembly_id}</strong>
                  <span>{a.quantity != null ? `${a.quantity} per assembly` : 'Quantity not stated'}</span>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </Section>

      <Section id="specifications" title="Specifications">
        {d.specifications.length === 0 ? (
          <p className="pds__none">No specifications are recorded for this part.</p>
        ) : (
          specGroups.map((group) => (
            <div key={group}>
              {group ? <h3 className="spec__group">{group}</h3> : null}
              <Facts rows={d.specifications.filter((s) => (s.group ?? '') === group).map((s) => [s.name, s.value ? `${s.value}${s.unit ? ` ${s.unit}` : ''}` : NOT_AVAILABLE])} />
            </div>
          ))
        )}
      </Section>

      <Section id="machines" title="Compatible machines" note="Fitment is recorded per machine model. Conditional fitment depends on the stated condition.">
        {d.fitment.length === 0 ? (
          <p className="pds__none">No fitment is recorded for this part.</p>
        ) : (
          <ul className="fit">
            {d.fitment.map((f) => {
              const ident = d.identification.find((i) => i.model_code === f.model_code)
              return (
                <li key={f.machine_id}>
                  <div>
                    <Link className="fit__model" to={machinePath(f.model_code)}>
                      {f.model_code}
                    </Link>
                    <p className="fit__name">{f.name}</p>
                    {f.condition_note ? <p className="fit__meta">{f.condition_note}</p> : null}
                    {ident?.identification_needed ? <p className="fit__ident">{ident.reason ?? 'Machine identification needed'}</p> : null}
                  </div>
                  <span className={`comp__status ${f.fitment_status === 'CONFIRMED' ? 'is-ok' : 'is-warn'}`}>{f.fitment_status ? humanize(f.fitment_status) : 'Status not stated'}</span>
                </li>
              )
            })}
          </ul>
        )}
      </Section>

      <Section id="legacy" title="Legacy references" note={`Numbers this part was known by before the unified Noordveld number ${part.part_number}. They are references, not alternatives.`}>
        {d.legacy_references.length === 0 ? (
          <p className="pds__none">No legacy references are recorded for this part.</p>
        ) : (
          <table className="rates">
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
                  <th scope="row" className="mono">{l.legacy_part_number ?? NOT_AVAILABLE}</th>
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
        )}
      </Section>

      <Section id="supply" title="Supply and availability" note="Stock and supply values are demonstration data.">
        <div className="pdt__cols">
          <div>
            <h3>Warehouses</h3>
            {d.warehouses.length === 0 ? (
              <p className="pds__none">{NOT_CONFIGURED}</p>
            ) : (
              <ul className="pds__list">
                {d.warehouses.map((w) => (
                  <li key={w.warehouse_id}>
                    <strong>{w.name ?? w.warehouse_id}</strong>
                    <span>{place(w.city, w.country_code)}</span>
                    <span>{w.available != null ? `${w.available} available` : NOT_AVAILABLE}{w.stock_status ? ` · ${humanize(w.stock_status)}` : ''}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3>Dealers</h3>
            {d.dealers.length === 0 ? (
              <p className="pds__none">{NOT_CONFIGURED}</p>
            ) : (
              <ul className="pds__list">
                {d.dealers.map((x) => (
                  <li key={x.dealer_id}>
                    <strong>{x.name ?? x.dealer_id}</strong>
                    <span>{place(x.city, x.country_code)}</span>
                    <span>
                      {x.available != null ? `${x.available} available` : NOT_AVAILABLE}
                      {x.pickup_allowed ? ' · Collection possible' : ''}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3>Suppliers</h3>
            {d.suppliers.length === 0 ? (
              <p className="pds__none">{NOT_CONFIGURED}</p>
            ) : (
              <ul className="pds__list">
                {d.suppliers.map((s) => (
                  <li key={s.supplier_id}>
                    <strong>
                      {s.name ?? s.supplier_id}
                      {s.is_primary ? ' · Primary' : ''}
                    </strong>
                    <span>{place(s.city, s.country_code)}</span>
                    <span>{s.lead_time_days != null ? `Lead time ${s.lead_time_days} days` : 'Lead time not available'}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <p className="pds__none">Delivery options and fulfilment: {NOT_CONFIGURED}.</p>
      </Section>

      {d.compliance.length > 0 ? (
        <Section id="compliance" title="Compliance">
          <ul className="pds__list">
            {d.compliance.map((c, i) => (
              <li key={i}>
                <strong>{c.requirement ?? c.standard ?? c.certification}</strong>
                <span>{[c.standard, c.certificate_status ? humanize(c.certificate_status) : null, c.valid_until ? `valid until ${c.valid_until}` : null].filter(Boolean).join(' · ')}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {d.related.length > 0 ? (
        <Section id="related" title="Related parts" note="Connected in the catalogue. Interchangeability is not established.">
          <ul className="prel__grid">
            {d.related.map((r) => (
              <li key={`${r.part_id}-${r.relation}`}>
                <Link to={partPath(r.part_number)} className="prel__card">
                  <PartImage partNumber={r.part_number} category={r.category} name={r.name} variant="mini" />
                  <span>
                    <strong>{r.name}</strong>
                    <span className="mono">{r.part_number}</span>
                    <em>{RELATION[r.relation]}</em>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section id="provenance" title="Where this data comes from">
        <Facts
          rows={[
            ['Part record', part.data_status ? humanize(part.data_status) : NOT_AVAILABLE],
            ['Confidence', part.confidence ? humanize(part.confidence) : NOT_AVAILABLE],
            ['Source', [part.source_sheet, part.source_record_id].filter(Boolean).join(' · ') || NOT_AVAILABLE],
            ['Price, stock and supply', price?.data_status ? humanize(price.data_status) : NOT_AVAILABLE],
          ]}
        />
        <p className="pds__none">Demonstration store: none of the data here is authoritative for ordering.</p>
      </Section>
    </article>
  )
}
