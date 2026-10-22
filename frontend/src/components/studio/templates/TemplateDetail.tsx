import { useEffect, useRef, useState } from 'react'
import { Laptop, Smartphone, Tablet, X } from 'lucide-react'
import type { AppTemplate, TemplateModule } from '../../../api/appTemplates'
import { TemplateApp, type Device } from '../../../templates/TemplateApp'

const MODULE_LABEL: Record<TemplateModule['status'], string> = {
  supported: 'Included',
  configurable: 'Configurable',
  requires_integration: 'Needs an integration',
}

const DEVICES: { id: Device; label: string; Icon: typeof Laptop }[] = [
  { id: 'desktop', label: 'Desktop', Icon: Laptop },
  { id: 'tablet', label: 'Tablet', Icon: Tablet },
  { id: 'mobile', label: 'Mobile', Icon: Smartphone },
]

/** Inspect a template before choosing it: a live interactive preview at three widths, its pages, modules and limits. */
export function TemplateDetail({
  template,
  onClose,
  onUse,
  using,
  selected,
}: {
  template: AppTemplate
  onClose: () => void
  onUse?: () => void
  using?: boolean
  selected?: boolean
}) {
  const [device, setDevice] = useState<Device>('desktop')
  const [page, setPage] = useState(template.pages[0].id)
  const close = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    close.current?.focus()
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  const current = template.pages.find((item) => item.id === page) ?? template.pages[0]
  return (
    <div
      className="tg-overlay"
      role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="tg-detail" role="dialog" aria-modal="true" aria-labelledby="tg-detail-title">
        <header className="tg-detail__head">
          <div>
            <p className="tg-eyebrow">
              {template.category} · version {template.version} ·{' '}
              {template.status === 'stable' ? 'Stable' : 'Preview'}
            </p>
            <h2 id="tg-detail-title">{template.name}</h2>
            <p className="tg-muted">{template.description}</p>
          </div>
          <div className="tg-detail__actions">
            {onUse ? (
              <button
                type="button"
                className="tg-primary"
                onClick={onUse}
                disabled={using || selected}
              >
                {selected
                  ? 'Selected for this project'
                  : using
                    ? 'Selecting…'
                    : 'Use this template'}
              </button>
            ) : null}
            <button
              ref={close}
              type="button"
              className="tg-icon"
              onClick={onClose}
              aria-label="Close preview"
            >
              <X size={20} aria-hidden="true" />
            </button>
          </div>
        </header>
        <div className="tg-detail__body">
          <section className="tg-stage" aria-label="Live preview">
            <div className="tg-stage__bar">
              <div className="tg-segment" role="group" aria-label="Preview width">
                {DEVICES.map(({ id, label, Icon }) => (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={device === id}
                    onClick={() => setDevice(id)}
                  >
                    <Icon size={16} aria-hidden="true" /> {label}
                  </button>
                ))}
              </div>
              <span className="tg-muted">Interactive preview with fictional sample records</span>
            </div>
            <div className={`tg-stage__frame tg-stage__frame--${device}`}>
              <TemplateApp template={template} device={device} page={page} onPage={setPage} />
            </div>
          </section>
          <aside className="tg-facts">
            <section>
              <h3>{current.title}</h3>
              <p className="tg-muted">{current.purpose}</p>
              {current.users.length ? (
                <p className="tg-small">For {current.users.join(', ')}</p>
              ) : null}
            </section>
            <section>
              <h3>Pages</h3>
              <ul className="tg-pages">
                {template.pages.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      aria-current={item.id === page ? 'page' : undefined}
                      onClick={() => setPage(item.id)}
                    >
                      {item.title}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h3>Modules</h3>
              <ul className="tg-modules">
                {template.modules.map((module) => (
                  <li key={module.id}>
                    <span className={`tg-status tg-status--${module.status}`}>
                      {MODULE_LABEL[module.status]}
                    </span>
                    <span>
                      {module.name}
                      {module.note ? <small>{module.note}</small> : null}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
            {template.limitations.length ? (
              <section>
                <h3>Not included</h3>
                <ul className="tg-limits">
                  {template.limitations.map((text) => (
                    <li key={text}>{text}</li>
                  ))}
                </ul>
              </section>
            ) : null}
            <section>
              <h3>Design</h3>
              <p className="tg-muted">
                <strong>{template.theme.label}.</strong> {template.theme.direction}
              </p>
              <Swatches template={template} />
            </section>
          </aside>
        </div>
      </div>
    </div>
  )
}

export function Swatches({ template }: { template: AppTemplate }) {
  const c = template.theme.colors
  return (
    <span className="tg-swatches" aria-hidden="true">
      {[c.nav_background, c.primary, c.accent, c.surface_alt, c.background].map((color, index) => (
        <i key={index} style={{ background: color }} />
      ))}
    </span>
  )
}
