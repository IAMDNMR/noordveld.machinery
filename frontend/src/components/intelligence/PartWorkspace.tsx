import { ArrowLeft } from 'lucide-react'
import { useEffect, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { getPartOverview, type PartOverview, type PartTab } from '../../api'
import { useApi } from '../../hooks/useApi'
import { useIdentification } from '../../store/identification'
import { PartImage } from '../store/PartImage'
import { GraphTab } from './GraphTab'
import { ErrorNotice } from './Notices'
import { ProvenanceBadge } from './provenance'
import { ActionTab, InsightsTab, ProvenanceTab } from './tabs/InsightTabs'
import { AssemblyTab, FitmentTab, OverviewTab, RelatedTab } from './tabs/OverviewTabs'
import { ComplianceTab, DealersTab, InventoryTab, SuppliersTab } from './tabs/SupplyTabs'

export const TABS: readonly { id: PartTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'fitment', label: 'Machine & Fitment' },
  { id: 'related', label: 'Related Parts' },
  { id: 'assembly', label: 'Assembly / Components' },
  { id: 'suppliers', label: 'Supplier Intelligence' },
  { id: 'dealers', label: 'Dealer / Location' },
  { id: 'inventory', label: 'Inventory / Availability' },
  { id: 'compliance', label: 'Compliance' },
  { id: 'graph', label: 'Graph Relationships' },
  { id: 'provenance', label: 'Data & Provenance' },
  { id: 'insights', label: 'Intelligence / Insights' },
  { id: 'store', label: 'Parts Store Action' },
]

interface Props {
  partKey: string
  tab: PartTab
  /** what the way back reads: the investigation it came from, or Parts Intelligence */
  backLabel: string
  onTab: (tab: PartTab) => void
  onOpenPart: (partNumber: string) => void
  onClose: () => void
}

/** One part under investigation, as a document: identity first and dominant, a section index, then the open section. */
export function PartWorkspace({ partKey, tab, backLabel, onTab, onOpenPart, onClose }: Props) {
  const overview = useApi((s) => getPartOverview(partKey, s), `overview:${partKey}`)

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [partKey])

  const moveTab = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    e.preventDefault()
    const next = TABS[(index + step + TABS.length) % TABS.length]
    onTab(next.id)
    requestAnimationFrame(() => document.getElementById(`pw-tab-${next.id}`)?.focus())
  }

  const data = overview.data
  return (
    <article className="wf-container pw" aria-labelledby="pw-title">
      <button type="button" className="back-link" onClick={onClose}>
        <ArrowLeft size={14} strokeWidth={2} aria-hidden="true" /> {backLabel}
      </button>

      {overview.error ? (
        <ErrorNotice error={overview.error} onRetry={overview.reload} title={overview.error.notFound ? 'Part not found' : 'This part could not be loaded'} />
      ) : !data ? (
        <p className="pw-loading" role="status">
          Loading part…
        </p>
      ) : (
        <>
          <nav className="breadcrumbs" aria-label="Breadcrumb">
            <Link to="/">Home</Link>
            <span className="crumb-sep">/</span>
            <button type="button" className="crumb-btn" onClick={onClose}>
              Parts Intelligence
            </button>
            <span className="crumb-sep">/</span>
            <span className="crumb-current" aria-current="page">
              {data.part_number}
            </span>
          </nav>

          <header className="pi-header card card-pad">
            <div className="pi-head-img">
              <PartImage partNumber={data.part_number} category={data.category} name={data.name} />
            </div>
            <div className="pi-head-main">
              {data.category ? <p className="small muted">{data.category}</p> : null}
              <h1 id="pw-title" className="pi-pn">
                {data.part_number}
              </h1>
              <p className="pi-name">{data.name}</p>
              <p className="small muted">{[data.families.join(', '), data.subcategory].filter(Boolean).join(' · ')}</p>
              <div className="pi-head-badges">
                <span className="small muted">Status</span>
                <StatusBadge overview={data} />
                <span className="small muted">Data</span>
                <ProvenanceBadge value={data.data_class} />
              </div>
              {data.status.data_class === 'SYNTHETIC_DEMO' ? <p className="pw__demo-note">Status and orderability come from demo data, not a live catalogue.</p> : null}
            </div>
            <div className="pi-head-action">
              <PartActions overview={data} onIdentify={() => onTab('store')} />
            </div>
          </header>

          <div className="pi-tabs" role="tablist" aria-label="Part intelligence sections">
            {TABS.map((t, i) => (
              <button
                key={t.id}
                id={`pw-tab-${t.id}`}
                type="button"
                role="tab"
                className={`pi-tab ${tab === t.id ? 'is-active' : ''}`}
                aria-selected={tab === t.id}
                aria-controls="pw-panel"
                tabIndex={tab === t.id ? 0 : -1}
                onClick={() => onTab(t.id)}
                onKeyDown={(e) => moveTab(e, i)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="pw__body" id="pw-panel" role="tabpanel" aria-labelledby={`pw-tab-${tab}`}>
            <TabContent tab={tab} partKey={data.part_number} overview={data} onTab={onTab} onOpenPart={onOpenPart} />
          </div>
        </>
      )}
    </article>
  )
}

/** The status as the catalogue states it, plus what this user has already done about it (never a change of status). */
export function StatusBadge({ overview }: { overview: PartOverview }) {
  const { record } = useIdentification(overview.part_number)
  const { code, label } = overview.status
  const requested = code === 'UNVERIFIED' && record?.requestedAt
  return (
    <span className={`pw__status pw__status--${code.toLowerCase()}`}>
      {requested ? 'Identification requested' : label}
      {!requested && code !== 'VERIFIED' && record?.submittedAt ? <span className="pw__status-sub"> · details submitted</span> : null}
    </span>
  )
}

/** One primary action per status, as the API defines it. */
export function PartActions({ overview, onIdentify }: { overview: PartOverview; onIdentify: () => void }) {
  const { record, request } = useIdentification(overview.part_number)
  const action = overview.actions[0]
  if (!action) return null
  return (
    <div className="pw__actions">
      {action.kind === 'parts_store' && action.href ? (
        <Link className="btn btn-primary" to={action.href}>
          {action.label}
        </Link>
      ) : action.kind === 'identify' ? (
        <button type="button" className="btn btn-primary" onClick={onIdentify}>
          {action.label}
        </button>
      ) : action.kind === 'request_identification' ? (
        <button type="button" className="btn btn-primary" onClick={request} disabled={Boolean(record?.requestedAt)}>
          {record?.requestedAt ? 'Identification requested' : action.label}
        </button>
      ) : null}
    </div>
  )
}

function TabContent({ tab, partKey, overview, onTab, onOpenPart }: { tab: PartTab; partKey: string; overview: PartOverview; onTab: (t: PartTab) => void; onOpenPart: (pn: string) => void }) {
  switch (tab) {
    case 'overview':
      return <OverviewTab overview={overview} onTab={onTab} />
    case 'fitment':
      return <FitmentTab partKey={partKey} overview={overview} />
    case 'related':
      return <RelatedTab partKey={partKey} onOpen={onOpenPart} />
    case 'assembly':
      return <AssemblyTab partKey={partKey} onOpen={onOpenPart} />
    case 'suppliers':
      return <SuppliersTab partKey={partKey} />
    case 'dealers':
      return <DealersTab partKey={partKey} />
    case 'inventory':
      return <InventoryTab partKey={partKey} />
    case 'compliance':
      return <ComplianceTab partKey={partKey} />
    case 'graph':
      return <GraphTab partKey={partKey} onOpen={onOpenPart} />
    case 'provenance':
      return <ProvenanceTab partKey={partKey} />
    case 'insights':
      return <InsightsTab partKey={partKey} />
    case 'store':
      return <ActionTab overview={overview} onOpenFitment={() => onTab('fitment')} />
  }
}
