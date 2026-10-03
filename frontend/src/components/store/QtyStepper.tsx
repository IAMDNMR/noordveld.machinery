import { Minus, Plus } from 'lucide-react'

interface QtyStepperProps {
  value: number
  onChange: (qty: number) => void
  label: string
  min?: number
  max?: number
  compact?: boolean
}

export function QtyStepper({ value, onChange, label, min = 1, max = 99, compact = false }: QtyStepperProps) {
  return (
    <div className={`qty ${compact ? 'qty--compact' : ''}`} role="group" aria-label={label}>
      <button type="button" onClick={() => onChange(Math.max(min, value - 1))} disabled={value <= min} aria-label="Decrease quantity">
        <Minus size={16} strokeWidth={2} aria-hidden="true" />
      </button>
      <output aria-live="polite">{value}</output>
      <button type="button" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max} aria-label="Increase quantity">
        <Plus size={16} strokeWidth={2} aria-hidden="true" />
      </button>
    </div>
  )
}
