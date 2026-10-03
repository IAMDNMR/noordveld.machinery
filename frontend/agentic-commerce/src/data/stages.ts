export type StageId = 'commerce' | 'e-commerce' | 'quick-commerce' | 'agentic-e-commerce'

export interface Stage {
  id: StageId
  name: string
  idea: string
  summary: string
  flow: readonly string[]
}

export const stages: readonly Stage[] = [
  {
    id: 'commerce',
    name: 'Commerce',
    idea: 'I need something.',
    summary: 'Commerce begins with a need and a transaction between a customer and a seller. The customer drives the process, from asking to paying to receiving.',
    flow: ['Need', 'Seller', 'Product', 'Transaction', 'Delivery', 'Service'],
  },
  {
    id: 'e-commerce',
    name: 'E-Commerce',
    idea: 'I know what I want. Help me buy it online.',
    summary: 'Discovery, comparison and purchase move online. Customers can reach any seller from anywhere, but they still do most of the investigating and deciding themselves.',
    flow: ['Search', 'Browse', 'Filter', 'Compare', 'Purchase'],
  },
  {
    id: 'quick-commerce',
    name: 'Quick Commerce',
    idea: 'I know what I want. Get it to me quickly.',
    summary: 'Time becomes part of the experience. Availability, proximity, fulfilment and delivery speed matter as much as the product, in every category, not only groceries.',
    flow: ['Inventory', 'Nearby availability', 'Fulfilment', 'Delivery'],
  },
  {
    id: 'agentic-e-commerce',
    name: 'Agentic E-Commerce',
    idea: 'I have a need. Understand it and help me solve it.',
    summary: 'The starting point is no longer a known product. It is a need, a problem, an objective, with a budget, an urgency and constraints that matter.',
    flow: ['Need', 'Understand', 'Evaluate', 'Recommend', 'Act'],
  },
]
