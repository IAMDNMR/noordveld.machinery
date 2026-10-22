import { useState } from 'react'
import { Menu } from 'lucide-react'
import type { AppTemplate, SampleRow } from '../api/appTemplates'
import { TemplateBlock } from './components'
import { iconFor } from './icons'
import { themeStyle } from './theme'
import './TemplateApp.css'

export type Device = 'desktop' | 'tablet' | 'mobile'

type Props = {
  template: AppTemplate
  device?: Device
  page?: string
  /** Gallery thumbnails: show the first page only, without interaction. */
  still?: boolean
  onPage?: (page: string) => void
}

const matches = (row: SampleRow, query: string) =>
  !query ||
  Object.values(row).some((value) => String(value).toLowerCase().includes(query.toLowerCase()))

/**
 * Renders any template from its definition alone: theme tokens, navigation style, pages and components. The gallery,
 * the template preview and (in the next phase) the generated application all use this one engine.
 */
export function TemplateApp({ template, device = 'desktop', page, still, onPage }: Props) {
  const [ownPage, setOwnPage] = useState(template.pages[0].id)
  const [query, setQuery] = useState('')
  const [menu, setMenu] = useState(false)
  const active = template.pages.find((item) => item.id === (page ?? ownPage)) ?? template.pages[0]
  const go = (id: string) => {
    setOwnPage(id)
    setQuery('')
    setMenu(false)
    onPage?.(id)
  }
  const theme = template.theme
  const classes = [
    'ta',
    `ta--${device}`,
    `ta--nav-${template.nav_style}`,
    `ta--${theme.density}`,
    `ta--card-${theme.card_style}`,
    `ta--table-${theme.table_style}`,
    theme.touch ? 'ta--touch' : '',
    still ? 'ta--still' : '',
  ]
  const nav = (
    <nav className={`ta-nav${menu ? ' is-open' : ''}`} aria-label={`${template.name} navigation`}>
      {template.pages.map((item) => {
        const Icon = iconFor(item.icon)
        return (
          <button
            key={item.id}
            type="button"
            className={item.id === active.id ? 'is-active' : undefined}
            aria-current={item.id === active.id ? 'page' : undefined}
            onClick={() => go(item.id)}
            tabIndex={still ? -1 : undefined}
          >
            <Icon size={18} aria-hidden="true" />
            <span>{item.title}</span>
          </button>
        )
      })}
    </nav>
  )
  return (
    <div
      className={classes.filter(Boolean).join(' ')}
      style={themeStyle(theme)}
      inert={still || undefined}
    >
      <header className="ta-bar">
        <strong className="ta-brand">{template.name}</strong>
        {device === 'mobile' && template.nav_style !== 'bottom_tabs' ? (
          <button
            type="button"
            className="ta-menu"
            aria-expanded={menu}
            onClick={() => setMenu(!menu)}
          >
            <Menu size={20} aria-hidden="true" />
            <span className="ta-sr">Menu</span>
          </button>
        ) : null}
        <span className="ta-sample" title="The records shown are fictional examples">
          Sample data
        </span>
      </header>
      {nav}
      <main className="ta-main">
        <div className="ta-page-head">
          <h2>{active.title}</h2>
          <p>{active.purpose}</p>
        </div>
        <div className="ta-grid">
          {active.components.map((component, index) => (
            <section
              key={index}
              className={`ta-block ta-span-${component.span} ta-block--${component.type}`}
            >
              {component.title && component.type !== 'filter_bar' ? (
                <h3>{component.title}</h3>
              ) : null}
              <TemplateBlock
                component={component}
                rows={(component.role ? (template.sample[component.role] ?? []) : []).filter(
                  (row) => matches(row, query),
                )}
                query={query}
                onQuery={setQuery}
              />
            </section>
          ))}
        </div>
      </main>
    </div>
  )
}
