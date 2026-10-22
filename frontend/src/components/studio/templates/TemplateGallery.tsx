import { useCallback, useEffect, useMemo, useState } from 'react'
import { LayoutTemplate, RefreshCw, Search } from 'lucide-react'
import { listAppTemplates, type AppTemplate } from '../../../api/appTemplates'
import { isAbort } from '../../../api/client'
import { TemplateDetail, Swatches } from './TemplateDetail'
import { TemplateThumb } from './TemplateThumb'
import './templates.css'

type Sort = 'match' | 'name' | 'category'

/** The template library: search, filter by category, sort, preview and (inside a project) choose one. */
export function TemplateGallery({
  onUse,
  selectedId,
  usingId,
  ranking,
}: {
  onUse?: (template: AppTemplate) => void
  selectedId?: string | null
  usingId?: string | null
  /** Template ids in recommendation order, when there is a project to match against. */
  ranking?: string[]
}) {
  const [items, setItems] = useState<AppTemplate[] | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All')
  const [sort, setSort] = useState<Sort>(ranking?.length ? 'match' : 'name')
  const [open, setOpen] = useState<AppTemplate | null>(null)
  const load = useCallback((signal?: AbortSignal) => {
    listAppTemplates(signal)
      .then((data) => {
        setItems(data.templates)
        setError('')
      })
      .catch((cause) => {
        if (!isAbort(cause)) setError('The template library could not be loaded.')
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  const categories = useMemo(
    () => ['All', ...new Set((items ?? []).map((item) => item.category))],
    [items],
  )
  const shown = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean)
    const rank = (id: string) => {
      const index = ranking?.indexOf(id) ?? -1
      return index === -1 ? 99 : index
    }
    return (items ?? [])
      .filter((item) => category === 'All' || item.category === category)
      .filter((item) => {
        const text = [item.name, item.summary, item.category, ...item.keywords, ...item.users]
          .join(' ')
          .toLowerCase()
        return words.every((word) => text.includes(word))
      })
      .sort((a, b) =>
        sort === 'match'
          ? rank(a.id) - rank(b.id) || a.name.localeCompare(b.name)
          : sort === 'category'
            ? a.category.localeCompare(b.category) || a.name.localeCompare(b.name)
            : a.name.localeCompare(b.name),
      )
  }, [items, query, category, sort, ranking])

  if (error)
    return (
      <div className="tg-state" role="alert">
        <p>{error}</p>
        <button type="button" className="tg-secondary" onClick={() => (setError(''), load())}>
          <RefreshCw size={16} aria-hidden="true" /> Try again
        </button>
      </div>
    )
  return (
    <div className="tg">
      <div className="tg-tools">
        <label className="tg-search">
          <Search size={18} aria-hidden="true" />
          <span className="tg-sr">Search templates</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by domain, user or feature"
          />
        </label>
        <div className="tg-categories" role="group" aria-label="Category">
          {categories.map((name) => (
            <button
              key={name}
              type="button"
              aria-pressed={category === name}
              onClick={() => setCategory(name)}
            >
              {name}
            </button>
          ))}
        </div>
        <label className="tg-sort">
          <span>Sort</span>
          <select value={sort} onChange={(event) => setSort(event.target.value as Sort)}>
            {ranking?.length ? <option value="match">Best match</option> : null}
            <option value="name">Name</option>
            <option value="category">Category</option>
          </select>
        </label>
      </div>
      {items === null ? (
        <div className="tg-grid" aria-busy="true" aria-label="Loading templates">
          {[0, 1, 2].map((index) => (
            <div key={index} className="tg-card tg-card--loading" />
          ))}
        </div>
      ) : shown.length === 0 ? (
        <div className="tg-state">
          <LayoutTemplate size={28} aria-hidden="true" />
          <p>
            No template matches “{query}”{category !== 'All' ? ` in ${category}` : ''}.
          </p>
          <button
            type="button"
            className="tg-secondary"
            onClick={() => (setQuery(''), setCategory('All'))}
          >
            Show all templates
          </button>
        </div>
      ) : (
        <>
          <p className="tg-count" role="status">
            {shown.length} {shown.length === 1 ? 'template' : 'templates'}
          </p>
          <div className="tg-grid">
            {shown.map((item) => (
              <article
                key={item.id}
                className={`tg-card${item.id === selectedId ? ' is-selected' : ''}`}
              >
                <button
                  type="button"
                  className="tg-card__preview"
                  onClick={() => setOpen(item)}
                  aria-label={`Preview ${item.name}`}
                >
                  <TemplateThumb template={item} />
                </button>
                <div className="tg-card__body">
                  <p className="tg-eyebrow">
                    {item.category}
                    {item.status === 'preview' ? <span className="tg-badge">Preview</span> : null}
                    {item.id === selectedId ? (
                      <span className="tg-badge tg-badge--selected">Selected</span>
                    ) : null}
                  </p>
                  <h3>{item.name}</h3>
                  <p className="tg-muted">{item.summary}</p>
                  <p className="tg-small">
                    {item.pages.length} pages ·{' '}
                    {item.modules.filter((m) => m.status !== 'requires_integration').length} modules
                    · for {item.users.slice(0, 2).join(', ')}
                  </p>
                  <div className="tg-card__foot">
                    <span className="tg-theme">
                      <Swatches template={item} /> {item.theme.label}
                    </span>
                    <span className="tg-card__actions">
                      <button type="button" className="tg-secondary" onClick={() => setOpen(item)}>
                        Preview
                      </button>
                      {onUse ? (
                        <button
                          type="button"
                          className="tg-primary"
                          onClick={() => onUse(item)}
                          disabled={!!usingId || item.id === selectedId}
                        >
                          {item.id === selectedId
                            ? 'Selected'
                            : usingId === item.id
                              ? 'Selecting…'
                              : 'Use'}
                        </button>
                      ) : null}
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </>
      )}
      {open ? (
        <TemplateDetail
          template={open}
          onClose={() => setOpen(null)}
          onUse={onUse ? () => onUse(open) : undefined}
          using={usingId === open.id}
          selected={open.id === selectedId}
        />
      ) : null}
    </div>
  )
}
