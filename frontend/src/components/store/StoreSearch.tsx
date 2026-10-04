import { Search, X } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { searchParts } from '../../api'
import { useApi } from '../../hooks/useApi'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { formatMoney } from '../../lib/format'
import { partPath, STORE_ROUTE, toParams } from '../../lib/storeQuery'

const SUGGESTIONS = 6

/** Typeahead over the catalogue API. Suggestions are the API's own results; nothing is matched locally. */
export function StoreSearch({ variant }: { variant: 'hero' | 'bar' }) {
  const { pathname } = useLocation()
  const [params] = useSearchParams()
  const urlQuery = pathname === STORE_ROUTE ? (params.get('q') ?? '') : ''
  // Remount when the URL's query changes (back button, chip removal) so the box always shows what is being searched
  return <SearchBox key={urlQuery} variant={variant} initial={urlQuery} />
}

function SearchBox({ variant, initial }: { variant: 'hero' | 'bar'; initial: string }) {
  const navigate = useNavigate()
  const [text, setText] = useState(initial)
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const listId = useId()

  const term = useDebouncedValue(text.trim(), 250)
  const suggest = useApi(
    (signal) =>
      term.length < 2
        ? Promise.resolve(null)
        : searchParts({ q: term, category: '', machine: '', availability: [], orderable: false, sort: 'relevance', offset: 0, limit: SUGGESTIONS }, signal),
    term,
  )
  const items = suggest.data?.items ?? []
  const showList = open && term.length >= 2 && term === text.trim() && (suggest.data !== null || suggest.error !== null)

  useEffect(() => {
    const close = (e: PointerEvent) => !root.current?.contains(e.target as Node) && setOpen(false)
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])

  const resultsUrl = (q: string) => ({ pathname: STORE_ROUTE, search: toParams({ q }).toString() })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    setOpen(false)
    navigate(resultsUrl(text))
  }

  const links = () => Array.from(root.current?.querySelectorAll<HTMLAnchorElement>(`#${CSS.escape(listId)} a`) ?? [])
  const move = (e: KeyboardEvent, from: number, step: number) => {
    const all = links()
    if (!all.length) return
    e.preventDefault()
    const next = from + step
    if (next < 0) input.current?.focus()
    else all[Math.min(next, all.length - 1)]?.focus()
  }
  const onInputKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') setOpen(false)
    else if (e.key === 'ArrowDown' && showList) move(e, -1, 1)
  }
  const onLinkKey = (e: KeyboardEvent<HTMLAnchorElement>) => {
    const at = links().indexOf(document.activeElement as HTMLAnchorElement)
    if (e.key === 'ArrowDown') move(e, at, 1)
    else if (e.key === 'ArrowUp') move(e, at, -1)
    else if (e.key === 'Escape') {
      setOpen(false)
      input.current?.focus()
    }
  }

  return (
    <div className={`ssearch ssearch--${variant}`} ref={root}>
      <form role="search" onSubmit={submit} className={variant === 'hero' ? 'search-box' : undefined}>
        {variant === 'bar' ? <Search className="ssearch__icon" size={18} strokeWidth={1.8} aria-hidden="true" /> : null}
        <input
          ref={input}
          type="search"
          aria-label="Search parts, machines or part numbers"
          aria-controls={listId}
          placeholder={variant === 'hero' ? 'Search by part number, description or machine' : 'Search parts, machines or part numbers...'}
          value={text}
          autoComplete="off"
          onChange={(e) => {
            setText(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onInputKey}
        />
        {text ? (
          <button
            type="button"
            className="ssearch__clear"
            aria-label="Clear search"
            onClick={() => {
              setText('')
              if (initial) navigate(resultsUrl(''))
              input.current?.focus()
            }}
          >
            <X size={16} strokeWidth={2} aria-hidden="true" />
          </button>
        ) : null}
        {variant === 'hero' ? (
          <button type="submit" className="btn btn-primary">
            Search
          </button>
        ) : null}
      </form>
      <ul id={listId} className="ssearch__list" aria-label="Suggestions" hidden={!showList}>
        {suggest.error ? (
          <li className="ssearch__msg">Suggestions are unavailable right now.</li>
        ) : items.length === 0 ? (
          <li className="ssearch__msg">No parts match “{term}”.</li>
        ) : (
          <>
            {items.map((p) => (
              <li key={p.part_id}>
                <Link to={partPath(p.part_number)} onClick={() => setOpen(false)} onKeyDown={onLinkKey}>
                  <span className="ssearch__name">{p.name}</span>
                  <span className="ssearch__sub">{p.part_number}</span>
                  {p.price ? <span className="ssearch__price">{formatMoney(p.price)}</span> : null}
                </Link>
              </li>
            ))}
            <li className="ssearch__all">
              <Link to={resultsUrl(text)} onClick={() => setOpen(false)} onKeyDown={onLinkKey}>
                See all results for “{term}”
              </Link>
            </li>
          </>
        )}
      </ul>
    </div>
  )
}
