import { useRef, type CSSProperties } from 'react'
import { CountUp } from '../CountUp'
import { useInView } from '../../hooks/useInView'
import type { OrderRow, OrderStatus } from '../../api/orders'
import './order-pipeline.css'

/** Where each recorded status sits on the way from order to delivery. Anything off the main path is an exception. */
const STAGES: { name: string; statuses: OrderStatus[] }[] = [
  { name: 'Placed', statuses: ['NEW', 'CONFIRMED', 'PROCESSING'] },
  {
    name: 'Allocated',
    statuses: ['ALLOCATED', 'FULFILMENT_PENDING', 'FULFILLING', 'READY_TO_SHIP'],
  },
  { name: 'Shipped', statuses: ['SHIPPED'] },
  { name: 'Delivered', statuses: ['DELIVERED', 'COMPLETED'] },
]

/** The orders shown, counted per stage of the order pipeline, drawn as stations on one line. */
export function OrderPipeline({ orders }: { orders: readonly OrderRow[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, threshold: 0.3 })
  const counts = STAGES.map(
    (stage) => orders.filter((o) => stage.statuses.includes(o.status)).length,
  )
  const exceptions = orders.length - counts.reduce((n, c) => n + c, 0)
  const max = Math.max(1, ...counts)
  return (
    <div ref={ref} className={`opipe${inView ? ' is-in' : ''}`}>
      <ol aria-label="Orders by stage">
        {STAGES.map((stage, index) => (
          <li
            key={stage.name}
            style={{ '--i': index, '--h': counts[index] / max } as CSSProperties}
            data-empty={counts[index] === 0}
          >
            <span className="opipe__bar" aria-hidden="true">
              <i />
            </span>
            <span className="opipe__dot" aria-hidden="true" />
            <strong>
              <CountUp value={counts[index]} />
            </strong>
            <span>{stage.name}</span>
          </li>
        ))}
      </ol>
      <p className={`opipe__exceptions${exceptions ? ' has-some' : ''}`}>
        {exceptions
          ? `${exceptions} ${exceptions === 1 ? 'order needs' : 'orders need'} attention (cancelled, rejected or held).`
          : 'No orders are held, cancelled or rejected.'}
      </p>
    </div>
  )
}
