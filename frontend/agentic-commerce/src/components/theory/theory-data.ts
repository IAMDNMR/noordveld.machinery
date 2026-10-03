export interface TheoryStage {
  id: 'commerce' | 'e-commerce' | 'q-commerce' | 'agentic-commerce'
  no: string
  name: string
  statement: string
  body: string
  /** The characteristics of the stage, in the order they happen */
  traits: readonly string[]
  idea: string
  /** editorial image name in src/assets/editorial */
  image: string
  imageAlt: string
}

/** Conceptual only: nothing here describes the demo scenario that follows. */
export const THEORY_STAGES: readonly TheoryStage[] = [
  {
    id: 'commerce',
    no: '01',
    name: 'Commerce',
    statement: 'Need meets supply.',
    body: 'Traditional commerce connected people to products through physical sellers, catalogues and direct transactions. Whoever needed something had to know where to go for it.',
    traits: ['Physical sellers', 'Catalogues', 'Direct transactions'],
    idea: 'The buyer finds the seller.',
    image: 'machinery-at-work',
    imageAlt: 'A wheel loader at work on a gravel site.',
  },
  {
    id: 'e-commerce',
    no: '02',
    name: 'E-Commerce',
    statement: 'Commerce moved online.',
    body: 'Products became searchable and transactions became digital. The seller no longer had to be nearby, but the buyer still had to know what to look for.',
    traits: ['Search', 'Discover', 'Compare', 'Buy'],
    idea: 'The buyer finds the product.',
    image: 'mechanical-detail',
    imageAlt: 'Close detail of a hydraulic arm and wheel on a machine.',
  },
  {
    id: 'q-commerce',
    no: '03',
    name: 'Q-Commerce',
    statement: 'Speed became part of the experience.',
    body: 'Commerce began optimizing not only for digital access but also for speed, fulfilment and delivery. Availability and time to arrival started to matter as much as the product itself.',
    traits: ['Availability', 'Speed', 'Fulfilment', 'Delivery'],
    idea: 'The buyer expects the product faster.',
    image: 'work-environment',
    imageAlt: 'A workshop with machines and technicians.',
  },
  {
    id: 'agentic-commerce',
    no: '04',
    name: 'Agentic Commerce',
    statement: 'Commerce begins to understand intent.',
    body: 'Instead of requiring the customer to know exactly what product, page or search term to use, an agent can interpret intent and coordinate the next steps.',
    traits: ['Understand intent', 'Use context', 'Connect information', 'Take action', 'Orchestrate the journey'],
    idea: 'The system helps understand what the buyer needs.',
    image: 'engineering',
    imageAlt: 'An engineer at a workstation with machine drawings on screen.',
  },
]

export const THEORY_TITLE = 'How Commerce Evolved'
export const THEORY_LEAD = 'Each generation removed friction from the buying journey.'
export const THEORY_OUTRO = ['From searching for products', 'to expressing intent.'] as const
export const THEORY_NEXT = 'Now see what Agentic Commerce looks like in practice.'
