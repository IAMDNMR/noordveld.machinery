import { Search, X } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { eur, partPath, searchParts, STORE_ROUTE } from '../../data/store'

interface StoreSearchProps {
  variant: 'hero' | 'bar'
}

/** Search across names, part numbers, old (legacy) numbers, categories and the machines a part fits. */
export function StoreSearch({ variant }: StoreSearchProps) {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const urlQuery = params.get('q') ?? ''
  const [value, setValue] = useState(urlQuery)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const listId = useId()
  const wrap = useRef<HTMLDivElement>(null)

  useEffect(() => setValue(urlQuery), [urlQuery])

  const results = value.trim() ? searchParts(value, 6) : []
  const show = open && results.length > 0

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    setOpen(false)
    const q = value.trim()
    navigate(q ? `${STORE_ROUTE}?q=${encodeURIComponent(q)}` : STORE_ROUTE)
  }

  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setActive((i) => Math.min(results.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(-1, i - 1))
    } else if (e.key === 'Escape') {
      setOpen(false)
      setActive(-1)
    } else if (e.key === 'Enter' && show && active >= 0) {
      e.preventDefault()
      setOpen(false)
      navigate(partPath(results[active]))
    }
  }

  return (
    <div
      ref={wrap}
      className={`ssearch ssearch--${variant}`}
      onBlur={(e) => {
        if (!wrap.current?.contains(e.relatedTarget as Node | null)) setOpen(false)
      }}
    >
      <form role="search" onSubmit={submit}>
        <Search className="ssearch__icon" size={variant === 'hero' ? 22 : 18} strokeWidth={1.8} aria-hidden="true" />
        <input
          type="search"
          value={value}
          placeholder={variant === 'hero' ? 'Search by part name, part number or machine, e.g. hydraulic hose NV-3200' : 'Search parts'}
          aria-label="Search parts"
          role="combobox"
          aria-expanded={show}
          aria-controls={listId}
          aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          autoComplete="off"
          onChange={(e) => {
            setValue(e.target.value)
            setOpen(true)
            setActive(-1)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
        />
        {value ? (
          <button
            type="button"
            className="ssearch__clear"
            aria-label="Clear search"
            onClick={() => {
              setValue('')
              if (urlQuery) navigate(STORE_ROUTE)
            }}
          >
            <X size={16} strokeWidth={2} aria-hidden="true" />
          </button>
        ) : null}
        {variant === 'hero' ? (
          <button type="submit" className="ssearch__go">
            Search
          </button>
        ) : null}
      </form>

      {show ? (
        <ul id={listId} className="ssearch__list" role="listbox" aria-label="Matching parts">
          {results.map((p, i) => (
            <li key={p.id} id={`${listId}-${i}`} role="option" aria-selected={i === active}>
              <a
                href={partPath(p)}
                className={i === active ? 'is-active' : undefined}
                onMouseDown={(e) => e.preventDefault()}
                onClick={(e) => {
                  e.preventDefault()
                  setOpen(false)
                  navigate(partPath(p))
                }}
              >
                <span className="ssearch__name">{p.name}</span>
                <span className="ssearch__sub">
                  <span className="mono">{p.no}</span> · {p.category}
                </span>
                <span className="ssearch__price">{eur(p.price)}</span>
              </a>
            </li>
          ))}
          <li className="ssearch__all" role="presentation">
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => submit()}>
              See all results for “{value.trim()}”
            </button>
          </li>
        </ul>
      ) : null}
    </div>
  )
}
