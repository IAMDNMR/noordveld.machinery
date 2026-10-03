import { ClipboardCheck, Crosshair, Eye, Layers, PackageCheck, Package, Scale, ScanSearch, Search, ShoppingBag, Store, Truck, User, Warehouse, Workflow, HandCoins, type LucideIcon } from 'lucide-react'

/*
  The hero is one scroll-driven transformation. Authoring unit: 0–100 across the whole pinned scroll.
  Everything on screen is a pure function of this value, so it scrubs forwards and backwards and survives a refresh.
*/

export const TOTAL = 100

/** Chapter windows in authoring units */
export const T = {
  open1: [1.5, 7.5],
  open2: [8, 14.5],
  s1: [14.5, 29.5],
  m1: [27.5, 32.5],
  s2: [31, 47],
  m2: [45.5, 50.5],
  s3: [49, 63],
  quiet: [62, 64.5],
  question: [64, 71.5],
  morph: [68.5, 75],
  m3: [72.5, 76.5],
  s4: [75.5, 88.5],
  finale: [88, 100],
} as const

export interface EvoNode {
  label: string
  icon: LucideIcon
}

/** The persistent nodes: the same elements re-labelled and re-iconed at every stage. */
export const NODES: readonly (readonly EvoNode[])[] = [
  [
    { label: 'Need', icon: User },
    { label: 'Seller', icon: Store },
    { label: 'Product', icon: Package },
    { label: 'Transaction', icon: HandCoins },
  ],
  [
    { label: 'Discover', icon: Eye },
    { label: 'Search', icon: Search },
    { label: 'Compare', icon: Scale },
    { label: 'Buy', icon: ShoppingBag },
  ],
  [
    { label: 'Search', icon: Search },
    { label: 'Order', icon: ClipboardCheck },
    { label: 'Fulfil', icon: Warehouse },
    { label: 'Deliver', icon: Truck },
  ],
  [
    { label: 'Intent', icon: Crosshair },
    { label: 'Understanding', icon: ScanSearch },
    { label: 'Context', icon: Layers },
    { label: 'Action', icon: Workflow },
    { label: 'Fulfilment', icon: PackageCheck },
  ],
]

export interface EvoStage {
  id: 'commerce' | 'e-commerce' | 'q-commerce' | 'agentic-commerce'
  title: string
  statement: string
  window: readonly [number, number]
  flow: readonly string[]
  /** The line the static (reduced-motion) version shows */
  summary: string
}

export const STAGES: readonly EvoStage[] = [
  { id: 'commerce', title: 'Commerce', statement: 'Need meets supply.', window: T.s1, flow: ['Need', 'Seller', 'Product', 'Transaction'], summary: 'The buyer knows what they need, finds the seller, and the transaction happens.' },
  { id: 'e-commerce', title: 'E-Commerce', statement: 'Commerce moved online.', window: T.s2, flow: ['Discover', 'Search', 'Compare', 'Buy'], summary: 'Before: I go to the seller. Now: I search for the product.' },
  { id: 'q-commerce', title: 'Q-Commerce', statement: 'Commerce became faster.', window: T.s3, flow: ['Search', 'Order', 'Fulfil', 'Deliver'], summary: 'E-Commerce made commerce digital. Q-Commerce made it immediate.' },
  { id: 'agentic-commerce', title: 'Agentic Commerce', statement: 'Commerce begins to understand intent.', window: T.s4, flow: ['Intent', 'Understanding', 'Context', 'Action', 'Fulfilment'], summary: 'Commerce no longer waits for every click. It understands what you mean, and it can move the journey forward.' },
]

export const OPENING = ['Commerce has always been about one thing.', 'Getting what you need.'] as const
export const QUESTION = 'But what if you don’t know what to search for?'
export const MORPHS = [
  ['SEARCH', 'INTENT'],
  ['CLICK', 'UNDERSTAND'],
  ['ORDER', 'ORCHESTRATE'],
] as const
export const AGENTIC_LINES = [
  { text: 'Commerce no longer waits for every click.', at: [77, 81.5] },
  { text: 'It understands what you mean.', at: [81, 85.5] },
  { text: 'It can move the journey forward.', at: [85, 89.5] },
] as const
export const FINALE_NAMES = ['Commerce', 'E-Commerce', 'Q-Commerce', 'Agentic Commerce'] as const
export const FINALE_LINE = 'The next evolution of commerce.'
