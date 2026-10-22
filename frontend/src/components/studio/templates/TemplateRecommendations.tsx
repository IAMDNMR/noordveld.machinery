import { useCallback, useEffect, useState } from 'react'
import { ChevronDown, LayoutTemplate } from 'lucide-react'
import {
  getTemplateRecommendations,
  listAppTemplates,
  selectAppTemplate,
  type AppTemplate,
  type CoverageStatus,
  type TemplateRecommendation,
  type TemplateSelection,
} from '../../../api/appTemplates'
import { ApiError, isAbort } from '../../../api/client'
import { TemplateDetail } from './TemplateDetail'
import { TemplateGallery } from './TemplateGallery'
import { TemplateThumb } from './TemplateThumb'
import './templates.css'

const STATUS_LABEL: Record<CoverageStatus, string> = {
  supported: 'Included',
  configurable: 'Configurable',
  requires_integration: 'Needs an integration',
  unsupported: 'Not covered',
}
const FIT_LABEL = { strong: 'Strong match', partial: 'Partial match', weak: 'Weak match' }

/** Screens & UI starts here: the templates that fit this project, why they fit, and what they would not cover. */
export function TemplateRecommendations({
  projectId,
  revision,
  canEdit,
  refresh,
}: {
  projectId: string
  revision: number
  /** null while this person's access is still loading. */
  canEdit: boolean | null
  refresh: () => Promise<unknown>
}) {
  const [data, setData] = useState<{
    selected: TemplateSelection | null
    recommendations: TemplateRecommendation[]
  } | null>(null)
  const [error, setError] = useState('')
  const [using, setUsing] = useState<string | null>(null)
  const [browse, setBrowse] = useState(false)
  const [library, setLibrary] = useState<Record<string, AppTemplate>>({})
  const [open, setOpen] = useState<AppTemplate | null>(null)

  const load = useCallback(
    (signal?: AbortSignal) =>
      Promise.all([getTemplateRecommendations(projectId, signal), listAppTemplates(signal)])
        .then(([result, all]) => {
          setData(result)
          setLibrary(Object.fromEntries(all.templates.map((item) => [item.id, item])))
          setError('')
        })
        .catch((cause) => {
          if (!isAbort(cause)) setError('Template recommendations could not be loaded.')
        }),
    [projectId],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  const use = async (template: { id: string; name: string }) => {
    setUsing(template.id)
    setError('')
    try {
      await selectAppTemplate(projectId, revision, template.id)
      await refresh()
      await load()
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : `${template.name} could not be selected.`,
      )
    } finally {
      setUsing(null)
    }
  }

  const selected = data?.selected?.template_id ?? null
  return (
    <section className="tr" aria-labelledby="tr-title">
      <header className="tr-head">
        <div>
          <p className="tg-eyebrow">Application template</p>
          <h2 id="tr-title">Templates that fit this application</h2>
          <p className="tg-muted">
            Matched to your requirements and domain. Pick one to configure; nothing is generated
            until you approve it.
          </p>
        </div>
        <button
          type="button"
          className="tg-secondary"
          aria-expanded={browse}
          onClick={() => setBrowse(!browse)}
        >
          <LayoutTemplate size={16} aria-hidden="true" />{' '}
          {browse ? 'Hide library' : 'Browse all templates'}
        </button>
      </header>
      {error ? (
        <p className="tr-error" role="alert">
          {error}
        </p>
      ) : null}
      {!data && !error ? <p className="tg-muted">Matching templates…</p> : null}
      {data && !data.recommendations.length ? (
        <p className="tg-muted">
          No template matches this request closely yet. Browse the library, or describe the
          application in more detail.
        </p>
      ) : null}
      {data?.recommendations.length ? (
        <ol className="tr-list">
          {data.recommendations.map((item) => {
            const counts = item.coverage.reduce<Record<string, number>>(
              (all, entry) => ({ ...all, [entry.status]: (all[entry.status] ?? 0) + 1 }),
              {},
            )
            return (
              <li
                key={item.template.id}
                className={`tr-item${item.template.id === selected ? ' is-selected' : ''}`}
              >
                {library[item.template.id] ? (
                  <button
                    type="button"
                    className="tr-thumb"
                    onClick={() => setOpen(library[item.template.id])}
                    aria-label={`Preview ${item.template.name}`}
                  >
                    <TemplateThumb template={library[item.template.id]} />
                  </button>
                ) : null}
                <div className="tr-item__main">
                  <p className="tg-eyebrow">
                    <span className={`tg-fit tg-fit--${item.fit}`}>{FIT_LABEL[item.fit]}</span>
                    {item.template.id === selected ? (
                      <span className="tg-badge tg-badge--selected">Selected</span>
                    ) : null}
                  </p>
                  <h3>{item.template.name}</h3>
                  {item.reasons.length ? (
                    <p className="tg-muted">{item.reasons.join(' · ')}</p>
                  ) : null}
                  {item.entity_mapping.length ? (
                    <p className="tg-small">
                      Uses your records:{' '}
                      {item.entity_mapping.map((map) => `${map.entity} as ${map.label}`).join(', ')}
                    </p>
                  ) : null}
                  {item.coverage.length ? (
                    <details className="tr-coverage">
                      <summary>
                        Requirements:{' '}
                        {Object.entries(counts)
                          .map(
                            ([status, count]) =>
                              `${count} ${STATUS_LABEL[status as CoverageStatus].toLowerCase()}`,
                          )
                          .join(', ')}
                        <ChevronDown size={16} aria-hidden="true" />
                      </summary>
                      <ul>
                        {item.coverage.map((entry) => (
                          <li key={entry.requirement_id}>
                            <span className={`tg-status tg-status--${entry.status}`}>
                              {STATUS_LABEL[entry.status]}
                            </span>
                            <span>
                              {entry.statement}
                              {entry.module ? <small>{entry.module}</small> : null}
                              {entry.note ? <small>{entry.note}</small> : null}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </div>
                {canEdit ? (
                  <button
                    type="button"
                    className="tg-primary"
                    disabled={!!using || item.template.id === selected}
                    onClick={() => void use({ id: item.template.id, name: item.template.name })}
                  >
                    {item.template.id === selected
                      ? 'Selected'
                      : using === item.template.id
                        ? 'Selecting…'
                        : 'Use this template'}
                  </button>
                ) : null}
              </li>
            )
          })}
        </ol>
      ) : null}
      {canEdit === false ? (
        <p className="tg-small">
          You can view templates; choosing one needs edit access to this project.
        </p>
      ) : null}
      {open ? (
        <TemplateDetail
          template={open}
          onClose={() => setOpen(null)}
          onUse={canEdit ? () => void use(open) : undefined}
          using={using === open.id}
          selected={open.id === selected}
        />
      ) : null}
      {browse ? (
        <TemplateGallery
          ranking={data?.recommendations.map((item) => item.template.id)}
          selectedId={selected}
          usingId={using}
          onUse={canEdit ? (template: AppTemplate) => void use(template) : undefined}
        />
      ) : null}
    </section>
  )
}
