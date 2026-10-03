import { X } from 'lucide-react'
import { useEffect, useRef, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { getPartOverview, type PartOverview, type PartTab } from '../../api'
import { useApi } from '../../hooks/useApi'
import { PartImage } from '../store/PartImage'
import { GraphTab } from './GraphTab'
import { ErrorNotice } from './Notices'
import { ProvenanceBadge } from './provenance'
import { InsightsTab, ProvenanceTab, StoreTab } from './tabs/InsightTabs'
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
  onTab: (tab: PartTab) => void
  onOpenPart: (partNumber: string) => void
  onClose: () => void
}

export function PartWorkspace({ partKey, tab, onTab, onOpenPart, onClose }: Props) {
  const overview = useApi((s) => getPartOverview(partKey, s), `overview:${partKey}`)
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    panel.current?.focus()
    const onKey = (e: globalThis.KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      opener?.focus?.()
    }
  }, [onClose])

  useEffect(() => {
    document.getElementById(`pw-tab-${tab}`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [tab])

  const moveTab = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (!step) return
    e.preventDefault()
    const next = TABS[(index + step + TABS.length) % TABS.length]
    onTab(next.id)
    requestAnimationFrame(() => document.getElementById(`pw-tab-${next.id}`)?.focus())
  }

  const data = overview.data
  return (
    <div className="pw">
      <button type="button" className="pw__scrim" onClick={onClose} tabIndex={-1} aria-label="Close part workspace" />
      <div className="pw__panel" role="dialog" aria-modal="true" aria-labelledby="pw-title" tabIndex={-1} ref={panel}>
        <button type="button" className="pw__close" onClick={onClose} aria-label="Close part workspace">
          <X size={22} strokeWidth={1.8} aria-hidden="true" />
        </button>

        {overview.error ? (
          <div className="pw__body">
            <ErrorNotice error={overview.error} onRetry={overview.reload} title={overview.error.notFound ? 'Part not found' : 'This part could not be loaded'} />
          </div>
        ) : !data ? (
          <div className="pw__body">
            <p className="pw-loading" role="status">
              Loading part…
            </p>
          </div>
        ) : (
          <>
            <header className="pw__head">
              <div className="pw__image">
                <PartImage partNumber={data.part_number} category={data.category} name={data.name} />
              </div>
              <div className="pw__id">
                <p className="pw__eyebrow">Part Intelligence</p>
                <h2 id="pw-title" className="pw__no mono">
                  {data.part_number}
                </h2>
                <p className="pw__name">{data.name}</p>
                <dl className="pw__meta">
                  <div>
                    <dt>Category</dt>
                    <dd>{data.category ?? 'Not available'}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd className={`pw__status pw__status--${data.status.code.toLowerCase()}`}>{data.status.label}</dd>
                  </div>
                  <div>
                    <dt>Data</dt>
                    <dd>
                      <ProvenanceBadge value={data.data_class} />
                    </dd>
                  </div>
                </dl>
                <PartActions overview={data} onIdentify={() => onTab('fitment')} />
              </div>
            </header>

            <div className="pw__tabs" role="tablist" aria-label="Part intelligence sections">
              {TABS.map((t, i) => (
                <button
                  key={t.id}
                  id={`pw-tab-${t.id}`}
                  type="button"
                  role="tab"
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
      </div>
    </div>
  )
}

function PartActions({ overview, onIdentify }: { overview: PartOverview; onIdentify: () => void }) {
  const store = overview.actions.find((a) => a.kind === 'parts_store')
  const identify = overview.actions.some((a) => a.kind === 'identify')
  if (!store && !identify) return null
  return (
    <div className="pw__actions">
      {store?.href ? (
        <Link className="button button--primary" to={store.href}>
          {store.label}
        </Link>
      ) : null}
      {identify ? (
        <button type="button" className="button button--secondary" onClick={onIdentify}>
          Identify Part
        </button>
      ) : null}
    </div>
  )
}

function TabContent({ tab, partKey, overview, onTab, onOpenPart }: { tab: PartTab; partKey: string; overview: PartOverview; onTab: (t: PartTab) => void; onOpenPart: (pn: string) => void }) {
  switch (tab) {
    case 'overview':
      return <OverviewTab overview={overview} />
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
      return <StoreTab overview={overview} onIdentify={() => onTab('fitment')} />
  }
}
