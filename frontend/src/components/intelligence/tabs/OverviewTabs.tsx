import { getPartAssemblies, getPartFitment, getPartRelated, type PartOverview, type PartTab } from '../../../api'
import { useApi } from '../../../hooks/useApi'
import { Investigation } from '../Investigation'
import { ProvenanceBadge } from '../provenance'
import { Empty, Facts, TabFrame } from './shared'

export function OverviewTab({ overview, onTab }: { overview: PartOverview; onTab: (tab: PartTab) => void }) {
  return (
    <>
      <Investigation overview={overview} onTab={onTab} />
      <section className="card card-pad pw-record">
      <h3 className="pw-sub">Part record</h3>
      <Facts
        rows={[
          ['Part number', <span className="mono" key="pn">{overview.part_number}</span>],
          ['Part name', overview.name],
          ['Description', overview.description],
          ['Category', overview.category],
          ['Subcategory', overview.subcategory],
          ['Manufacturer', overview.manufacturer],
          ['Plant of origin', overview.origin_plant],
          ['Status', overview.status.label],
          ['Data class', <ProvenanceBadge value={overview.data_class} key="dc" />],
          ['Source', overview.source],
          ['Last updated', overview.last_updated],
        ]}
      />
      </section>
      {overview.identification.length > 0 ? (
        <div className="pw-note">
          <h3>Identification required</h3>
          <ul>
            {overview.identification.map((i, n) => (
              <li key={n}>{[i.model_code, i.reason ?? i.needed].filter(Boolean).join(': ')}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  )
}

export function FitmentTab({ partKey, overview }: { partKey: string; overview: PartOverview }) {
  const state = useApi((s) => getPartFitment(partKey, s), `fitment:${partKey}`)
  return (
    <>
      <p className="pw-lead">Fitment is recorded per machine model. A part is only shown as fitting where the graph holds a fitment relationship.</p>
      {overview.identification.length > 0 ? (
        <div className="pw-note" id="identify">
          <h3>Identify the machine</h3>
          <p>This part needs the machine or serial range confirmed before it can be treated as a match.</p>
          <ul>
            {overview.identification.map((i, n) => (
              <li key={n}>{[i.model_code, i.reason ?? i.needed].filter(Boolean).join(': ')}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <TabFrame state={state} label="Fitment">
        {(rows) =>
          rows.length === 0 ? (
            <Empty>No machine fitment is recorded for this part.</Empty>
          ) : (
            <ul className="pw-rows">
              {rows.map((r) => (
                <li key={r.model_code}>
                  <h3 className="mono">{r.model_code}</h3>
                  <p className="pw-rows__sub">{r.name}</p>
                  <Facts rows={[['Machine type', r.machine_type], ['Family', r.family], ['Fitment', r.fitment_status], ['Condition', r.condition_note]]} />
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

export function RelatedTab({ partKey, onOpen }: { partKey: string; onOpen: (pn: string) => void }) {
  const state = useApi((s) => getPartRelated(partKey, s), `related:${partKey}`)
  return (
    <>
      <p className="pw-lead">Parts linked by an explicit graph relationship. A link does not mean the parts are alternatives, replacements or interchangeable.</p>
      <TabFrame state={state} label="Related parts">
        {(rows) =>
          rows.length === 0 ? (
            <Empty>No related-part relationships are recorded for this part.</Empty>
          ) : (
            <ul className="pw-rows">
              {rows.map((r) => (
                <li key={`${r.part_number}-${r.relation}`}>
                  <h3 className="mono">
                    <button type="button" className="rcard__open" onClick={() => onOpen(r.part_number)}>
                      {r.part_number}
                    </button>
                  </h3>
                  <p className="pw-rows__sub">{r.name}</p>
                  <Facts rows={[['Relationship', <span className="mono" key="r">{r.relation}</span>], ['Meaning', r.relation_label], ['Category', r.category], ['Interchangeability', r.interchangeability_status ?? 'Not established']]} />
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

export function AssemblyTab({ partKey, onOpen }: { partKey: string; onOpen: (pn: string) => void }) {
  const state = useApi((s) => getPartAssemblies(partKey, s), `assemblies:${partKey}`)
  return (
    <TabFrame state={state} label="Assemblies">
      {(rows) =>
        rows.length === 0 ? (
          <Empty>This part is not connected to any assembly in the graph.</Empty>
        ) : (
          <>
            <ul className="pw-rows">
              {rows.map((a) => (
                <li key={a.assembly_id}>
                  <h3>{a.name ?? a.assembly_id}</h3>
                  <Facts rows={[['Quantity in assembly', a.quantity?.toString()], ['BOM status', a.bom_status], ['Identified by part', a.identified_by], ['Components', a.component_count.toString()]]} />
                  {a.components.length > 0 ? (
                    <>
                      <h4 className="pw-sub">Other components</h4>
                      <ul className="pw-simple">
                        {a.components.map((c) => (
                          <li key={c.part_number}>
                            <button type="button" className="rcard__open mono" onClick={() => onOpen(c.part_number)}>
                              {c.part_number}
                            </button>
                            <span>{c.name}</span>
                            <span>{c.quantity === null ? 'Quantity not stated' : `× ${c.quantity}`}</span>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                  <ProvenanceBadge value={a.data_class} />
                </li>
              ))}
            </ul>
            <Empty>Machine association: not connected. The graph links assemblies to parts, not to machines.</Empty>
          </>
        )
      }
    </TabFrame>
  )
}
