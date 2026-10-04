import { getPartCompliance, getPartDealers, getPartInventory, getPartSuppliers } from '../../../api'
import { useApi } from '../../../hooks/useApi'
import { ProvenanceBadge } from '../provenance'
import { Empty, Facts, place, TabFrame, yesNo } from './shared'

export function SuppliersTab({ partKey }: { partKey: string }) {
  const state = useApi((s) => getPartSuppliers(partKey, s), `suppliers:${partKey}`)
  return (
    <>
      <p className="pw-lead">Only suppliers with an explicit SUPPLIED_BY relationship to this part are shown.</p>
      <TabFrame state={state} label="Suppliers">
        {(rows) =>
          rows.length === 0 ? (
            <Empty>No supplier relationship is recorded for this part.</Empty>
          ) : (
            <ul className="pw-rows">
              {rows.map((r) => (
                <li key={r.supplier_id}>
                  <h3>{r.name ?? r.supplier_id}</h3>
                  <Facts
                    rows={[
                      ['Relationship', <span className="mono" key="r">{r.relation}</span>],
                      ['Location', place(r.city, r.country_code)],
                      ['Primary supplier', yesNo(r.is_primary)],
                      ['Lead time', r.lead_time_days === null ? null : `${r.lead_time_days} days`],
                      ['Supplies categories', r.categories.join(', ') || null],
                    ]}
                  />
                  <ProvenanceBadge value={r.data_class} />
                </li>
              ))}
            </ul>
          )
        }
      </TabFrame>
    </>
  )
}

export function DealersTab({ partKey }: { partKey: string }) {
  const state = useApi((s) => getPartDealers(partKey, s), `dealers:${partKey}`)
  return (
    <>
      <p className="pw-lead">Dealers with a stocking record for this part. Locations are the city and country stated on each dealer; they say nothing about other relationships.</p>
      <TabFrame state={state} label="Dealers">
        {(rows) =>
          rows.length === 0 ? (
            <Empty>No dealer stocking relationship is recorded for this part.</Empty>
          ) : (
            <ul className="pw-rows">
              {rows.map((r) => (
                <li key={r.dealer_id}>
                  <h3>{r.name ?? r.dealer_id}</h3>
                  <Facts
                    rows={[
                      ['Relationship', <span className="mono" key="r">{r.relation}</span>],
                      ['City', r.city],
                      ['Country', r.country_code],
                      ['Stocking status', r.stocking_status],
                      ['Units recorded', r.available?.toString()],
                      ['Collection', yesNo(r.pickup_allowed)],
                    ]}
                  />
                  <ProvenanceBadge value={r.data_class} />
                </li>
              ))}
            </ul>
          )
        }
      </TabFrame>
    </>
  )
}

export function InventoryTab({ partKey }: { partKey: string }) {
  const state = useApi((s) => getPartInventory(partKey, s), `inventory:${partKey}`)
  return (
    <TabFrame state={state} label="Inventory">
      {(inv) =>
        inv.state === 'NOT_CONNECTED' ? (
          <div className="pw-note">
            <h3>{inv.availability_label ?? 'No inventory record'}</h3>
            <p>{inv.note}</p>
            <ProvenanceBadge value="NOT_CONNECTED" />
          </div>
        ) : (
          <>
            <Facts rows={[['Availability', inv.availability_label], ['Warehouse units recorded', inv.total_available?.toString()], ['Warehouses', inv.warehouses.length.toString()], ['Dealers with a record', inv.dealers.length.toString()], ['Data class', <ProvenanceBadge value={inv.data_class} key="d" />]]} />
            {inv.note ? <p className="pw-note-inline">{inv.note}</p> : null}
            {inv.warehouses.length > 0 ? (
              <>
                <h3 className="pw-sub">Warehouses</h3>
                <ul className="pw-rows">
                  {inv.warehouses.map((w) => (
                    <li key={w.warehouse_id}>
                      <h4>{w.name ?? w.warehouse_id}</h4>
                      <Facts rows={[['Location', place(w.city, w.country_code)], ['Units recorded', w.available?.toString()], ['Stock status', w.stock_status]]} />
                      <ProvenanceBadge value={w.data_class} />
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            {inv.dealers.length > 0 ? (
              <>
                <h3 className="pw-sub">Dealer stock</h3>
                <ul className="pw-rows">
                  {inv.dealers.map((d) => (
                    <li key={d.dealer_id}>
                      <h4>{d.name ?? d.dealer_id}</h4>
                      <Facts rows={[['Location', place(d.city, d.country_code)], ['Units recorded', d.available?.toString()], ['Stocking status', d.stocking_status]]} />
                      <ProvenanceBadge value={d.data_class} />
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            <p className="pw-empty">Delivery options and fulfilment: Not configured.</p>
          </>
        )
      }
    </TabFrame>
  )
}

export function ComplianceTab({ partKey }: { partKey: string }) {
  const state = useApi((s) => getPartCompliance(partKey, s), `compliance:${partKey}`)
  return (
    <TabFrame state={state} label="Compliance">
      {(rows) =>
        rows.length === 0 ? (
          <Empty>No compliance requirement is connected to this part.</Empty>
        ) : (
          <ul className="pw-rows">
            {rows.map((c, i) => (
              <li key={i}>
                <h3>{c.requirement ?? c.standard ?? 'Requirement'}</h3>
                <Facts rows={[['Standard', c.standard], ['Certification', c.certification], ['Certificate status', c.certificate_status], ['Valid until', c.valid_until], ['Covers categories', c.covers.join(', ') || null]]} />
                {c.data_class === 'SYNTHETIC_DEMO' ? <p className="pw-note-inline">Demonstration assignment, not a real certification.</p> : null}
                <ProvenanceBadge value={c.data_class} />
              </li>
            ))}
          </ul>
        )
      }
    </TabFrame>
  )
}
