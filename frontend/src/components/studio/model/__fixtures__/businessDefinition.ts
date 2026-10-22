import type { ApplicationDefinition } from '../../../../api/applicationDefinition'
import { emptyDefinition } from '../applicationDefinition'

/** Synthetic test design: one requirement, role, entity, decision rule, exception and a branching process. */
export function businessDefinition(): ApplicationDefinition {
  return {
    ...emptyDefinition(),
    id: 'app_business',
    business: {
      brief: {
        goal: 'Order spare parts',
        problem: '',
        domain_id: 'spare_parts_commerce',
        subdomain: '',
        capability: '',
        purpose: '',
        user_types: [],
        outcomes: [],
        constraints: [],
        dependencies: [],
      },
      requirements: [
        {
          id: 'req_order',
          statement: 'A customer can order a part.',
          kind: 'functional',
          category: null,
          priority: 'must',
          status: 'draft',
          acceptance_criteria: [{ id: 'ac_order', statement: 'An order is recorded.' }],
          deferral_reason: '',
          origin: null,
        },
      ],
      roles: [
        {
          id: 'role_customer',
          name: 'Customer',
          responsibilities: ['Orders parts'],
          permissions: ['orders.place'],
          approval_authority: [],
          origin: null,
        },
      ],
      entities: [
        {
          id: 'ent_order',
          name: 'Order',
          description: '',
          owner_role_id: null,
          source_system: '',
          origin: null,
          relationships: [],
          attributes: [
            {
              id: 'order_id',
              name: 'Order number',
              type: 'string',
              required: true,
              key: true,
              allow_unknown: false,
              description: '',
              validations: [],
            },
            {
              id: 'quantity',
              name: 'Quantity',
              type: 'integer',
              required: true,
              key: false,
              allow_unknown: false,
              description: '',
              validations: [],
            },
          ],
        },
      ],
      rules: [
        {
          id: 'rule_stock',
          description: 'Known stock must cover the quantity.',
          type: 'decision',
          status: 'confirmed',
          source: { kind: 'implemented_code', reference: 'app/services/checkout.py' },
          condition: '',
          outcomes: ['AVAILABLE', 'UNAVAILABLE'],
          origin: null,
        },
      ],
      exceptions: [
        {
          id: 'exc_no_stock',
          name: 'No stock',
          trigger: 'Stock is insufficient.',
          recovery: 'The order is not placed.',
          resolution: 'terminate',
          resolution_state_id: 'end_failed',
          origin: null,
        },
      ],
      decisions: [
        {
          id: 'dec_partial',
          question: 'Allow partial fulfilment?',
          status: 'open',
          answer: '',
          deferral_reason: '',
          affects: ['exc_no_stock'],
          origin: null,
        },
      ],
      integrations: [],
      terms: [],
      questions: [],
      knowledge: [],
    },
    workflows: ['wf_order'],
    workflow_definitions: [
      {
        version: 1,
        id: 'wf_order',
        name: 'Order',
        states: [
          { id: 'start', label: 'Start', kind: 'start', outputs: [], role_id: 'role_customer' },
          {
            id: 'enter_order',
            label: 'Enter order',
            kind: 'form',
            outputs: ['rule_stock'],
            role_id: 'role_customer',
            permission: 'orders.place',
            requirement_ids: ['req_order'],
            reads_entity_ids: [],
            writes_entity_ids: ['ent_order'],
            rule_ids: ['rule_stock'],
            exception_ids: [],
          },
          {
            id: 'no_stock',
            label: 'No stock',
            kind: 'exception',
            outputs: [],
            role_id: 'role_customer',
            requirement_ids: ['req_order'],
            exception_ids: ['exc_no_stock'],
          },
          { id: 'end_done', label: 'Ordered', kind: 'end', outputs: [], outcome: 'success' },
          { id: 'end_failed', label: 'Not ordered', kind: 'end', outputs: [], outcome: 'failure' },
        ],
        transitions: [
          {
            id: 't_start',
            source: 'start',
            target: 'enter_order',
            condition: { kind: 'always', field: null, value: null },
          },
          {
            id: 't_ok',
            source: 'enter_order',
            target: 'end_done',
            condition: { kind: 'equals', field: 'rule_stock', value: 'AVAILABLE' },
          },
          {
            id: 't_no',
            source: 'enter_order',
            target: 'no_stock',
            condition: { kind: 'equals', field: 'rule_stock', value: 'UNAVAILABLE' },
          },
          {
            id: 't_fail',
            source: 'no_stock',
            target: 'end_failed',
            condition: { kind: 'always', field: null, value: null },
          },
        ],
      },
    ],
  }
}

/** The same design after screen generation: one traced form screen with a navigation button. */
export function generatedDefinition(): ApplicationDefinition {
  const base = businessDefinition()
  const trace = {
    generated: true,
    workflow_id: 'wf_order',
    step_id: 'enter_order',
    requirement_ids: ['req_order'],
  }
  return {
    ...base,
    revision: 4,
    screens: [
      ...base.screens,
      {
        id: 'gen_enter_order',
        title: 'Enter order',
        trace,
        components: [
          {
            kind: 'container',
            id: 'gen_enter_order_section',
            props: {
              title: 'Order',
              layout: {
                mobile: { mode: 'stack', columns: 1 },
                tablet: { mode: 'grid', columns: 2 },
                desktop: { mode: 'grid', columns: 2 },
              },
            },
            placement: { span: 12 },
            trace: { ...trace, entity_id: 'ent_order' },
            children: [
              {
                kind: 'field',
                id: 'gen_enter_order_quantity',
                props: {
                  field_type: 'number',
                  label: 'Quantity',
                  help_text: null,
                  options: [],
                  validations: [
                    { kind: 'required', value: true, message: 'Quantity is required.' },
                  ],
                },
                placement: { span: 6 },
                binding: null,
                events: [],
                trace: { ...trace, entity_id: 'ent_order', attribute_id: 'quantity' },
              },
            ],
          },
          {
            kind: 'button',
            id: 'gen_enter_order_to_end_done',
            props: { label: 'If rule_stock = AVAILABLE: Ordered' },
            placement: { span: 12 },
            binding: null,
            events: [{ trigger: 'click', action: 'navigate', target: 'gen_end_done', value: null }],
            trace,
          },
        ],
      },
      {
        id: 'gen_end_done',
        title: 'Ordered',
        trace: {
          generated: true,
          workflow_id: 'wf_order',
          step_id: 'end_done',
          requirement_ids: [],
        },
        components: [
          {
            kind: 'text',
            id: 'gen_end_done_text',
            props: { content: 'Ordered. Completed successfully.' },
            placement: { span: 12 },
            binding: null,
            events: [],
            trace: {
              generated: true,
              workflow_id: 'wf_order',
              step_id: 'end_done',
              requirement_ids: [],
            },
          },
        ],
      },
    ],
  }
}
