import { Check, ChevronDown, Euro, MapPin, Target, X, Zap, type LucideIcon } from 'lucide-react'
import { useId, useMemo, useRef, useState } from 'react'
import { useInView } from '../../hooks/useInView'
import { demoOptions, demoRequirement, evaluate, formatPrice, priorities, type CommerceRecommendation, type Priority } from '../../lib/recommend'
import { Reveal } from '../ui/Reveal'

const priorityIcons: Record<Priority, LucideIcon> = {
  'best-match': Target,
  'lowest-price': Euro,
  'fastest-delivery': Zap,
  'closest-availability': MapPin,
}

const emphasis: Record<Priority, 'price' | 'availability' | 'distance' | null> = {
  'best-match': null,
  'lowest-price': 'price',
  'fastest-delivery': 'availability',
  'closest-availability': 'distance',
}

function statusFor(option: CommerceRecommendation, recommended: boolean, eligible: boolean, checks: ReturnType<typeof evaluate>['checks']): string {
  if (recommended) return 'Recommended'
  if (eligible) return 'Meets your requirement'
  const c = checks[option.id]
  if (!c.budget) return 'Over budget'
  if (!c.timeframe) return `Arrives ${option.deliveryTime.toLowerCase()}, outside your two days`
  return 'Not compatible'
}

export function Decision() {
  const [priority, setPriority] = useState<Priority>('best-match')
  const [open, setOpen] = useState(false)
  const groupName = useId()
  const panelId = useId()
  const listRef = useRef<HTMLOListElement>(null)
  const inView = useInView(listRef, { once: true, threshold: 0.3 })

  const result = useMemo(() => evaluate(demoRequirement, demoOptions, priority), [priority])
  const { recommended, checks, eligible } = result
  const key = emphasis[priority]
  const rc = checks[recommended.id]

  const evidence = [
    { ok: rc.budget, text: 'Meets budget', note: `${formatPrice(recommended.price)} of ${formatPrice(demoRequirement.budget)}` },
    { ok: rc.compatible, text: 'Compatible', note: 'Fits the machine in this example' },
    { ok: rc.timeframe, text: 'Available within required timeframe', note: recommended.availability },
    { ok: rc.location, text: 'Suitable location', note: `${recommended.distance} km away` },
  ]

  return (
    <section id="experience" className="section on-night decision" aria-labelledby="decision-title">
      <div className="container">
        <Reveal>
          <p className="eyebrow">Try it</p>
        </Reveal>
        <Reveal delay={80}>
          <h2 id="decision-title" className="h1 decision__title">
            Same requirement. Change what matters.
          </h2>
        </Reveal>
        <Reveal delay={160}>
          <p className="lead decision__lead">Agentic E-Commerce does not just sort a list. It weighs the options against the customer’s requirement and their priority, and explains its choice.</p>
        </Reveal>

        <dl className="decision__req">
          <div>
            <dt>Budget</dt>
            <dd>{formatPrice(demoRequirement.budget)}</dd>
          </div>
          <div>
            <dt>Needed</dt>
            <dd>Within two days</dd>
          </div>
          <div>
            <dt>Parts</dt>
            <dd>Compatible</dd>
          </div>
        </dl>

        <fieldset className="priority">
          <legend className="priority__legend">What matters most?</legend>
          <div className="priority__group">
            {priorities.map((p) => (
              <label key={p.id} className="priority__option">
                <input type="radio" name={groupName} value={p.id} checked={priority === p.id} onChange={() => setPriority(p.id)} />
                <span>
                  {(() => {
                    const Icon = priorityIcons[p.id]
                    return <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
                  })()}
                  {p.label}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <ol className={`options ${inView ? 'is-in' : ''}`} ref={listRef} aria-label="Options evaluated against the requirement">
          {demoOptions.map((o, i) => {
            const isRec = o.id === recommended.id
            const ok = eligible.has(o.id)
            return (
              <li key={o.id} className={`option ${isRec ? 'is-recommended' : ''} ${ok ? '' : 'is-excluded'}`} style={{ ['--i' as string]: i }}>
                <h3 className="option__name">Option {o.id}</h3>
                <p className={`option__cell ${key === 'price' ? 'is-key' : ''}`}>
                  <span className="option__caption">Price</span>
                  <span className="option__value">{formatPrice(o.price)}</span>
                </p>
                <p className={`option__cell ${key === 'availability' ? 'is-key' : ''}`}>
                  <span className="option__caption">Availability</span>
                  <span className="option__value">{o.availability}</span>
                </p>
                <p className={`option__cell ${key === 'distance' ? 'is-key' : ''}`}>
                  <span className="option__caption">Distance</span>
                  <span className="option__value">{o.distance} km</span>
                </p>
                <p className="option__status">{statusFor(o, isRec, ok, checks)}</p>
              </li>
            )
          })}
        </ol>

        <div className="verdict" aria-live="polite">
          <p className="verdict__label">Recommended</p>
          <p className="verdict__name h2">Option {recommended.id}</p>
          <p className="verdict__why">{result.explanation}</p>
          <button type="button" className="disclosure" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((v) => !v)}>
            Why this recommendation?
            <ChevronDown className="disclosure__icon" size={18} strokeWidth={2} aria-hidden="true" />
          </button>
          <div id={panelId} className="evidence" hidden={!open}>
            <ul>
              {evidence.map((e) => (
                <li key={e.text} className={e.ok ? 'is-ok' : 'is-fail'}>
                  {e.ok ? <Check size={20} strokeWidth={2.2} aria-hidden="true" /> : <X size={20} strokeWidth={2.2} aria-hidden="true" />}
                  <span>
                    {e.text}
                    <small>{e.note}</small>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <p className="decision__note">Demonstration data. The options, prices and availability above are sample values, not live inventory, suppliers or payments.</p>
      </div>
    </section>
  )
}
