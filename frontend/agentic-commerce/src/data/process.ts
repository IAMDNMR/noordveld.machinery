import { BadgeCheck, Cog, Factory, Fingerprint, Layers, MapPin, Puzzle, Replace, ScanSearch, Scale, Search, ShoppingBag, PackageCheck, Tag, Target, ThumbsUp, Warehouse, CircleCheck, type LucideIcon } from 'lucide-react'

export interface ProcessStep {
  id: string
  icon: LucideIcon
  name: string
  question: string
  detail?: string
}

/** The user-facing stages of turning a requirement into an outcome. No model internals are shown. */
export const processSteps: readonly ProcessStep[] = [
  { id: 'understand', icon: Target, name: 'Understand', question: 'What does the customer actually need?', detail: 'A broken machine and a deadline is not a request for a product. It is a need to be operational again.' },
  { id: 'context', icon: ScanSearch, name: 'Context', question: 'What machine, product or environment is involved?', detail: 'Machine, model and assembly give the need a precise setting.' },
  { id: 'discover', icon: Search, name: 'Discover', question: 'What possible solutions exist?', detail: 'Parts, alternatives and suppliers that could restore the machine.' },
  { id: 'verify', icon: BadgeCheck, name: 'Verify', question: 'Which solutions are compatible?', detail: 'Only options that genuinely fit the machine move forward.' },
  { id: 'evaluate', icon: Scale, name: 'Evaluate', question: 'How do the options compare against what matters?', detail: 'Price, budget, availability, location, delivery, alternatives and the customer’s own priorities.' },
  { id: 'recommend', icon: ThumbsUp, name: 'Recommend', question: 'Which option best matches the requirement?', detail: 'The option that best matches the stated requirements and the available evidence.' },
  { id: 'act', icon: ShoppingBag, name: 'Act', question: 'With the customer’s approval, make it happen.', detail: 'Purchase, then fulfilment, then delivery.' },
]

export interface RelationNode {
  id: string
  icon: LucideIcon
  label: string
  /** Index of the process step at which this node becomes part of the picture. */
  litAt: number
}

/** Underlying relationships the system draws on. Presented as context, not as a stage of commerce. */
export const relationNodes: readonly RelationNode[] = [
  { id: 'machine', icon: Cog, label: 'Machine', litAt: 1 },
  { id: 'model', icon: Tag, label: 'Model', litAt: 1 },
  { id: 'assembly', icon: Layers, label: 'Assembly', litAt: 1 },
  { id: 'part', icon: Puzzle, label: 'Part', litAt: 2 },
  { id: 'compatibility', icon: BadgeCheck, label: 'Compatibility', litAt: 3 },
  { id: 'alternative', icon: Replace, label: 'Alternative', litAt: 2 },
  { id: 'supplier', icon: Factory, label: 'Supplier', litAt: 2 },
  { id: 'inventory', icon: Warehouse, label: 'Inventory', litAt: 4 },
  { id: 'location', icon: MapPin, label: 'Location', litAt: 4 },
]

export interface JourneyStop {
  label: string
  icon: LucideIcon
}

export const journey: readonly JourneyStop[] = [
  { label: 'Need', icon: Target },
  { label: 'Understand', icon: ScanSearch },
  { label: 'Discover', icon: Search },
  { label: 'Evaluate', icon: Scale },
  { label: 'Recommend', icon: ThumbsUp },
  { label: 'Approve', icon: Fingerprint },
  { label: 'Purchase', icon: ShoppingBag },
  { label: 'Fulfil', icon: PackageCheck },
  { label: 'Outcome', icon: CircleCheck },
]
