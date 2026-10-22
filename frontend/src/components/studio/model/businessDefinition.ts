import type {
  ApplicationDefinition,
  BusinessDefinition,
  Trace,
} from '../../../api/applicationDefinition'

/** Mirrors the backend's business-section checks (shape, unique IDs, references). The backend stays authoritative. */
type RecordValue = Record<string, unknown>
const record = (value: unknown): value is RecordValue =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
const allowed = (value: RecordValue, keys: string[]) =>
  Object.keys(value).every((key) => keys.includes(key))
export const ID = /^[a-z][a-z0-9_-]{1,79}$/
const id = (value: unknown): value is string => typeof value === 'string' && ID.test(value)
const optId = (value: unknown) => value === undefined || value === null || id(value)
const text = (value: unknown, min: number, max: number) =>
  typeof value === 'string' && value.length >= min && value.length <= max
const optText = (value: unknown, max: number) => value === undefined || text(value, 0, max)
const optBool = (value: unknown) => value === undefined || typeof value === 'boolean'
const oneOf = (value: unknown, options: readonly string[]) =>
  typeof value === 'string' && options.includes(value)
const optOneOf = (value: unknown, options: readonly string[]) =>
  value === undefined || value === null || oneOf(value, options)
const texts = (value: unknown, max: number, itemMax: number) =>
  Array.isArray(value) && value.length <= max && value.every((item) => text(item, 1, itemMax))
const optTexts = (value: unknown, max: number, itemMax: number) =>
  value === undefined || texts(value, max, itemMax)
const unique = (values: unknown[]) => new Set(values).size === values.length
const ids = (value: unknown, max = 30) =>
  Array.isArray(value) && value.length <= max && value.every(id) && unique(value)
const optIds = (value: unknown, max = 30) => value === undefined || ids(value, max)
export const PERMISSION = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/
export const OUTCOME = /^[A-Za-z][A-Za-z0-9_]*$/

export const REQUIREMENT_CATEGORIES = [
  'security',
  'usability',
  'performance',
  'accessibility',
  'auditability',
  'reliability',
  'compliance',
  'other',
] as const
export const ATTRIBUTE_TYPES = [
  'string',
  'integer',
  'decimal',
  'boolean',
  'date',
  'datetime',
] as const
export const CARDINALITIES = ['one_to_one', 'one_to_many', 'many_to_one', 'many_to_many'] as const
export const RULE_SOURCES = [
  'business_owner',
  'implemented_code',
  'document',
  'graph_data',
  'workshop',
  'synthetic_assumption',
] as const
export const STEP_KINDS = [
  'start',
  'form',
  'search',
  'review',
  'approval',
  'branch',
  'action',
  'exception',
  'end',
] as const

const origin = (value: unknown) =>
  value === undefined ||
  value === null ||
  (record(value) &&
    allowed(value, ['pack_id', 'pack_version', 'item_id']) &&
    id(value.pack_id) &&
    text(value.pack_version, 1, 40) &&
    id(value.item_id))
/** One validation rule on a field or attribute; mirrors the backend `Validation` model. */
export const validationRule = (value: unknown) =>
  record(value) &&
  allowed(value, ['kind', 'value', 'message']) &&
  oneOf(value.kind, [
    'required',
    'email',
    'min_length',
    'max_length',
    'pattern',
    'minimum',
    'maximum',
  ]) &&
  (value.value === undefined ||
    value.value === null ||
    ['string', 'number', 'boolean'].includes(typeof value.value)) &&
  (value.message === undefined || value.message === null || text(value.message, 0, 500)) &&
  (value.kind !== 'pattern' ||
    ['digits', 'letters', 'alphanumeric'].includes(value.value as string)) &&
  (!['minimum', 'maximum'].includes(value.kind as string) ||
    (typeof value.value === 'number' && Number.isFinite(value.value)))

function brief(value: unknown): boolean {
  return (
    record(value) &&
    allowed(value, [
      'goal',
      'problem',
      'domain_id',
      'subdomain',
      'capability',
      'purpose',
      'user_types',
      'outcomes',
      'constraints',
      'dependencies',
    ]) &&
    optText(value.goal, 2000) &&
    optText(value.problem, 2000) &&
    optId(value.domain_id) &&
    optText(value.subdomain, 120) &&
    optText(value.capability, 200) &&
    optText(value.purpose, 1000) &&
    optTexts(value.user_types, 30, 200) &&
    optTexts(value.outcomes, 30, 300) &&
    optTexts(value.constraints, 50, 300) &&
    optTexts(value.dependencies, 50, 300)
  )
}

function requirement(value: unknown): boolean {
  if (
    !record(value) ||
    !allowed(value, [
      'id',
      'statement',
      'kind',
      'category',
      'priority',
      'status',
      'acceptance_criteria',
      'deferral_reason',
      'origin',
    ]) ||
    !id(value.id) ||
    !text(value.statement, 1, 1000) ||
    !optOneOf(value.kind, ['functional', 'non_functional']) ||
    !optOneOf(value.category, REQUIREMENT_CATEGORIES) ||
    !oneOf(value.priority, ['must', 'should', 'could', 'wont']) ||
    !oneOf(value.status, ['draft', 'agreed', 'deferred', 'rejected']) ||
    !optText(value.deferral_reason, 1000) ||
    !origin(value.origin)
  )
    return false
  if (value.kind === 'non_functional' && !value.category) return false
  const criteria = value.acceptance_criteria
  return (
    Array.isArray(criteria) &&
    criteria.length <= 20 &&
    criteria.every(
      (item) =>
        record(item) &&
        allowed(item, ['id', 'statement']) &&
        id(item.id) &&
        text(item.statement, 1, 500),
    ) &&
    unique(criteria.map((item) => (item as RecordValue).id))
  )
}

function role(value: unknown): boolean {
  return (
    record(value) &&
    allowed(value, [
      'id',
      'name',
      'responsibilities',
      'permissions',
      'approval_authority',
      'origin',
    ]) &&
    id(value.id) &&
    text(value.name, 1, 120) &&
    texts(value.responsibilities ?? [], 30, 300) &&
    Array.isArray(value.permissions) &&
    value.permissions.length <= 50 &&
    value.permissions.every(
      (item) => typeof item === 'string' && item.length <= 80 && PERMISSION.test(item),
    ) &&
    unique(value.permissions) &&
    optTexts(value.approval_authority, 20, 300) &&
    origin(value.origin)
  )
}

const optNumber = (value: unknown) =>
  value === undefined || value === null || (typeof value === 'number' && Number.isFinite(value))
const optLength = (value: unknown) =>
  value === undefined ||
  value === null ||
  (typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 10000)
export const VALUE_SOURCES = ['user_entered', 'system_generated', 'calculated', 'imported'] as const
export const FORMATS = [
  'email',
  'phone',
  'url',
  'postal_code',
  'currency_amount',
  'percentage',
] as const
export const SENSITIVITIES = ['public', 'internal', 'personal', 'confidential'] as const

/** Attribute shape and metadata coherence; mirrors the backend `EntityAttribute` checks. */
export function attributeError(value: unknown): string | null {
  if (
    !record(value) ||
    !allowed(value, [
      'id',
      'name',
      'type',
      'required',
      'key',
      'allow_unknown',
      'description',
      'validations',
      'value_source',
      'writable',
      'default',
      'format',
      'minimum',
      'maximum',
      'min_length',
      'max_length',
      'pattern',
      'enum',
      'sensitivity',
      'owner_role_id',
      'reference',
    ]) ||
    !id(value.id) ||
    !text(value.name, 1, 120) ||
    !oneOf(value.type, ATTRIBUTE_TYPES) ||
    !optBool(value.required) ||
    !optBool(value.key) ||
    !optBool(value.allow_unknown) ||
    !optText(value.description, 500) ||
    !optBool(value.writable) ||
    !(
      value.validations === undefined ||
      (Array.isArray(value.validations) &&
        value.validations.length <= 20 &&
        value.validations.every(validationRule))
    ) ||
    !optOneOf(value.value_source, VALUE_SOURCES) ||
    !optOneOf(value.format, FORMATS) ||
    !optOneOf(value.pattern, ['digits', 'letters', 'alphanumeric']) ||
    !optOneOf(value.sensitivity, SENSITIVITIES) ||
    !optNumber(value.minimum) ||
    !optNumber(value.maximum) ||
    !optLength(value.min_length) ||
    !optLength(value.max_length) ||
    !optId(value.owner_role_id) ||
    !(
      value.enum === undefined ||
      (Array.isArray(value.enum) &&
        value.enum.length <= 50 &&
        value.enum.every((item) => text(item, 1, 80)) &&
        unique(value.enum))
    ) ||
    !(
      value.default === undefined ||
      value.default === null ||
      ['string', 'number', 'boolean'].includes(typeof value.default)
    ) ||
    !(
      value.reference === undefined ||
      value.reference === null ||
      (record(value.reference) &&
        allowed(value.reference, ['entity_id', 'attribute_id']) &&
        id(value.reference.entity_id) &&
        id(value.reference.attribute_id))
    )
  )
    return 'Attribute fields are invalid.'
  const numeric = value.type === 'integer' || value.type === 'decimal'
  if (value.key && (!value.required || value.allow_unknown))
    return 'A key attribute must be required and cannot be unknown.'
  if ((value.value_source ?? 'user_entered') !== 'user_entered' && value.writable !== false)
    return 'A system-managed attribute cannot be writable by users.'
  if ((value.minimum ?? null) !== null || (value.maximum ?? null) !== null) {
    if (!numeric) return 'Minimum and maximum apply to numbers only.'
    if (
      value.minimum != null &&
      value.maximum != null &&
      (value.minimum as number) > (value.maximum as number)
    )
      return 'Minimum is greater than maximum.'
  }
  if (
    (value.min_length != null ||
      value.max_length != null ||
      value.pattern ||
      value.format ||
      (Array.isArray(value.enum) && value.enum.length)) &&
    value.type !== 'string'
  )
    return 'Length, pattern, format and allowed values apply to text only.'
  if (
    value.min_length != null &&
    value.max_length != null &&
    (value.min_length as number) > (value.max_length as number)
  )
    return 'Minimum length is greater than maximum length.'
  if (value.default != null) {
    if (Array.isArray(value.enum) && value.enum.length && !value.enum.includes(value.default))
      return 'The default is not one of the allowed values.'
    const expected = value.type === 'boolean' ? 'boolean' : numeric ? 'number' : 'string'
    if (
      typeof value.default !== expected ||
      (value.type === 'integer' && !Number.isInteger(value.default))
    )
      return 'The default does not match the attribute type.'
  }
  return null
}
const attribute = (value: unknown) => attributeError(value) === null

function isEntity(value: unknown): boolean {
  if (
    !record(value) ||
    !allowed(value, [
      'id',
      'name',
      'description',
      'owner_role_id',
      'source_system',
      'attributes',
      'relationships',
      'origin',
    ]) ||
    !id(value.id) ||
    !text(value.name, 1, 120) ||
    !optText(value.description, 1000) ||
    !optId(value.owner_role_id) ||
    !optText(value.source_system, 200) ||
    !origin(value.origin)
  )
    return false
  const { attributes, relationships } = value
  return (
    Array.isArray(attributes) &&
    attributes.length <= 60 &&
    attributes.every(attribute) &&
    unique(attributes.map((item) => (item as RecordValue).id)) &&
    Array.isArray(relationships) &&
    relationships.length <= 30 &&
    unique(relationships.map((item) => (item as RecordValue).id)) &&
    relationships.every(
      (item) =>
        record(item) &&
        allowed(item, ['id', 'name', 'target', 'cardinality', 'required']) &&
        id(item.id) &&
        text(item.name, 1, 120) &&
        id(item.target) &&
        oneOf(item.cardinality, CARDINALITIES) &&
        (item.required === undefined || typeof item.required === 'boolean'),
    )
  )
}

function execution(value: unknown): boolean {
  if (value === undefined || value === null) return true
  if (
    !record(value) ||
    !allowed(value, [
      'kind',
      'field',
      'operator',
      'other_field',
      'value',
      'pass_outcome',
      'fail_outcome',
    ])
  )
    return false
  const ref = (item: unknown) =>
    typeof item === 'string' && /^[a-z][a-z0-9_-]*\.[a-z][a-z0-9_-]*$/.test(item)
  return (
    oneOf(value.kind, ['compare', 'value']) &&
    ref(value.field) &&
    optOneOf(value.operator, ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'present']) &&
    (value.other_field == null || ref(value.other_field)) &&
    (value.value == null || ['string', 'number', 'boolean'].includes(typeof value.value)) &&
    (value.pass_outcome == null || text(value.pass_outcome, 1, 60)) &&
    (value.fail_outcome == null || text(value.fail_outcome, 1, 60))
  )
}

function rule(value: unknown): boolean {
  if (
    !record(value) ||
    !execution(value.execution) ||
    !allowed(value, [
      'id',
      'description',
      'type',
      'status',
      'source',
      'condition',
      'outcomes',
      'origin',
      'execution',
    ]) ||
    !id(value.id) ||
    !text(value.description, 1, 1000) ||
    !optOneOf(value.type, ['validation', 'decision', 'calculation', 'policy']) ||
    !oneOf(value.status, ['confirmed', 'assumption']) ||
    !optText(value.condition, 1000) ||
    !origin(value.origin)
  )
    return false
  const source = value.source
  if (
    !record(source) ||
    !allowed(source, ['kind', 'reference']) ||
    !oneOf(source.kind, RULE_SOURCES) ||
    !text(source.reference, 1, 300)
  )
    return false
  const outcomes = value.outcomes ?? []
  if (
    !Array.isArray(outcomes) ||
    outcomes.length > 20 ||
    !outcomes.every(
      (item) => typeof item === 'string' && item.length <= 60 && OUTCOME.test(item),
    ) ||
    !unique(outcomes)
  )
    return false
  if (value.status === 'confirmed' && source.kind === 'synthetic_assumption') return false
  return !(value.type === 'decision' && outcomes.length < 2)
}

const exception = (value: unknown) =>
  record(value) &&
  allowed(value, [
    'id',
    'name',
    'trigger',
    'recovery',
    'resolution',
    'resolution_state_id',
    'origin',
  ]) &&
  id(value.id) &&
  text(value.name, 1, 120) &&
  text(value.trigger, 1, 500) &&
  text(value.recovery, 1, 1000) &&
  optOneOf(value.resolution, ['recover', 'terminate', 'escalate']) &&
  optId(value.resolution_state_id) &&
  ((value.resolution ?? null) === null) === ((value.resolution_state_id ?? null) === null) &&
  origin(value.origin)
const decision = (value: unknown) =>
  record(value) &&
  allowed(value, ['id', 'question', 'status', 'answer', 'deferral_reason', 'affects', 'origin']) &&
  id(value.id) &&
  text(value.question, 1, 500) &&
  optOneOf(value.status, ['open', 'decided', 'deferred']) &&
  optText(value.answer, 1000) &&
  optText(value.deferral_reason, 1000) &&
  optIds(value.affects, 50) &&
  origin(value.origin)
const integration = (value: unknown) =>
  record(value) &&
  allowed(value, [
    'id',
    'name',
    'system',
    'direction',
    'events',
    'entity_ids',
    'failure_handling',
    'contract_status',
    'origin',
  ]) &&
  id(value.id) &&
  text(value.name, 1, 120) &&
  text(value.system, 1, 120) &&
  oneOf(value.direction, ['inbound', 'outbound', 'bidirectional']) &&
  optTexts(value.events, 30, 120) &&
  optIds(value.entity_ids) &&
  optText(value.failure_handling, 1000) &&
  optOneOf(value.contract_status, ['defined', 'deferred']) &&
  origin(value.origin)
const term = (value: unknown) =>
  record(value) &&
  allowed(value, ['id', 'term', 'definition', 'origin']) &&
  id(value.id) &&
  text(value.term, 1, 120) &&
  text(value.definition, 1, 1000) &&
  origin(value.origin)
const question = (value: unknown) =>
  record(value) &&
  allowed(value, ['id', 'topic', 'text', 'answer', 'status']) &&
  id(value.id) &&
  text(value.topic, 1, 60) &&
  text(value.text, 1, 500) &&
  optText(value.answer, 2000) &&
  optOneOf(value.status, ['open', 'answered', 'not_applicable'])

const GROUPS = {
  requirements: [requirement, 200],
  roles: [role, 50],
  entities: [isEntity, 100],
  rules: [rule, 200],
  exceptions: [exception, 100],
  decisions: [decision, 100],
  integrations: [integration, 50],
  terms: [term, 200],
} as const

export function emptyBusiness(): BusinessDefinition {
  return {
    brief: {
      goal: '',
      problem: '',
      domain_id: null,
      subdomain: '',
      capability: '',
      purpose: '',
      user_types: [],
      outcomes: [],
      constraints: [],
      dependencies: [],
    },
    requirements: [],
    roles: [],
    entities: [],
    rules: [],
    exceptions: [],
    decisions: [],
    integrations: [],
    terms: [],
    questions: [],
    knowledge: [],
  }
}

/** Shape, unique IDs and the section's internal references. Returns an error message or null. */
export function businessError(value: unknown): string | null {
  if (
    !record(value) ||
    !allowed(value, [
      'brief',
      'requirements',
      'roles',
      'entities',
      'rules',
      'exceptions',
      'decisions',
      'integrations',
      'terms',
      'questions',
      'knowledge',
    ])
  )
    return 'The business section has unsupported fields.'
  if (value.brief !== undefined && !brief(value.brief)) return 'The business brief is invalid.'
  const all: string[] = []
  for (const [name, [check, max]] of Object.entries(GROUPS)) {
    const items = value[name] ?? []
    if (name === 'entities' && Array.isArray(items)) {
      for (const item of items) {
        const bad =
          record(item) && Array.isArray(item.attributes)
            ? item.attributes.map(attributeError).find(Boolean)
            : null
        if (bad) return `${String(item.id)}: ${bad}`
      }
    }
    if (!Array.isArray(items) || items.length > max || !items.every(check))
      return `Invalid ${name.replace('_', ' ')} in the business section.`
    all.push(...items.map((item) => (item as RecordValue).id as string))
  }
  if (!unique(all))
    return 'Business IDs must be unique across requirements, roles, entities, rules, exceptions, decisions, integrations and terms.'
  const questions = value.questions ?? []
  if (
    !Array.isArray(questions) ||
    questions.length > 100 ||
    !questions.every(question) ||
    !unique(questions.map((item) => (item as RecordValue).id))
  )
    return 'Discovery questions are invalid.'
  const knowledge = value.knowledge ?? []
  if (
    !Array.isArray(knowledge) ||
    knowledge.length > 10 ||
    !knowledge.every(
      (item) =>
        record(item) &&
        allowed(item, ['pack_id', 'pack_version']) &&
        id(item.pack_id) &&
        text(item.pack_version, 1, 40),
    )
  )
    return 'Knowledge links are invalid.'
  const business = value as unknown as BusinessDefinition
  const entityIds = new Set((business.entities ?? []).map((item) => item.id))
  const roleIds = new Set((business.roles ?? []).map((item) => item.id))
  if (
    (business.entities ?? []).some((item) =>
      item.relationships.some((relation) => !entityIds.has(relation.target)),
    )
  )
    return 'A relationship refers to an unknown entity.'
  if (
    (business.entities ?? []).some((item) => item.owner_role_id && !roleIds.has(item.owner_role_id))
  )
    return 'An entity owner refers to an unknown role.'
  if (
    (business.integrations ?? []).some((item) =>
      (item.entity_ids ?? []).some((ref) => !entityIds.has(ref)),
    )
  )
    return 'An integration refers to an unknown entity.'
  const attributeIds = new Map(
    (business.entities ?? []).map((item) => [
      item.id,
      new Set(item.attributes.map((member) => member.id)),
    ]),
  )
  for (const entity of business.entities ?? []) {
    for (const member of entity.attributes) {
      if (member.owner_role_id && !roleIds.has(member.owner_role_id))
        return `Attribute ${entity.id}.${member.id} has an unknown owner role.`
      if (
        member.reference &&
        !attributeIds.get(member.reference.entity_id)?.has(member.reference.attribute_id)
      )
        return `Attribute ${entity.id}.${member.id} refers to an unknown attribute.`
    }
  }
  return null
}

export function traceError(value: unknown): boolean {
  if (value === undefined || value === null) return false
  if (
    !record(value) ||
    !allowed(value, [
      'generated',
      'workflow_id',
      'step_id',
      'requirement_ids',
      'entity_id',
      'attribute_id',
      'relationship_id',
      'rule_id',
      'exception_id',
      'source_sha256',
    ])
  )
    return true
  if (!(
    value.source_sha256 === undefined ||
    value.source_sha256 === null ||
    (typeof value.source_sha256 === 'string' && /^[0-9a-f]{64}$/.test(value.source_sha256))
  ))
    return true
  if (
    !optBool(value.generated) ||
    !optId(value.workflow_id) ||
    !optId(value.step_id) ||
    !optIds(value.requirement_ids) ||
    !optId(value.entity_id) ||
    !optId(value.attribute_id) ||
    !optId(value.relationship_id) ||
    !optId(value.rule_id) ||
    !optId(value.exception_id)
  )
    return true
  return (
    (!!value.step_id && !value.workflow_id) ||
    (!!value.attribute_id && !value.entity_id) ||
    (!!value.relationship_id && !value.entity_id)
  )
}

/** References between the business section, workflow steps and screen traces. */
export function crossReferenceError(definition: ApplicationDefinition): string | null {
  const business = definition.business ?? emptyBusiness()
  const requirementIds = new Set(business.requirements.map((item) => item.id))
  const entities = new Map(
    business.entities.map((item) => [item.id, new Set(item.attributes.map((member) => member.id))]),
  )
  const roles = new Map(business.roles.map((item) => [item.id, new Set(item.permissions)]))
  const rules = new Map(business.rules.map((item) => [item.id, new Set(item.outcomes ?? [])]))
  const exceptionIds = new Set(business.exceptions.map((item) => item.id))
  const workflows = new Map(
    (definition.workflow_definitions ?? []).map((workflow) => [
      workflow.id,
      new Set(workflow.states.map((state) => state.id)),
    ]),
  )
  const allStates = new Set([...workflows.values()].flatMap((states) => [...states]))
  for (const workflow of definition.workflow_definitions ?? []) {
    for (const state of workflow.states) {
      if (state.role_id && !roles.has(state.role_id))
        return `Step "${state.label}" refers to an unknown role.`
      if (state.permission && (!state.role_id || !roles.get(state.role_id)!.has(state.permission)))
        return `Step "${state.label}" requires a permission its role does not hold.`
      if ((state.requirement_ids ?? []).some((ref) => !requirementIds.has(ref)))
        return `Step "${state.label}" refers to an unknown requirement.`
      if (
        [...(state.reads_entity_ids ?? []), ...(state.writes_entity_ids ?? [])].some(
          (ref) => !entities.has(ref),
        )
      )
        return `Step "${state.label}" refers to an unknown entity.`
      for (const [mapping, relationships] of [
        [state.input_fields, false],
        [state.input_relationships, true],
      ] as const) {
        for (const [entityId, refs] of Object.entries(mapping ?? {})) {
          const entity = business.entities.find((item) => item.id === entityId)
          const members = relationships ? entity?.relationships : entity?.attributes
          if (
            !(state.writes_entity_ids ?? []).includes(entityId) ||
            refs.some((ref) => !members?.some((item) => item.id === ref))
          )
            return `Step "${state.label}" has unresolved task inputs.`
        }
      }
      if ((state.rule_ids ?? []).some((ref) => !rules.has(ref)))
        return `Step "${state.label}" refers to an unknown rule.`
      if ((state.exception_ids ?? []).some((ref) => !exceptionIds.has(ref)))
        return `Step "${state.label}" refers to an unknown exception.`
    }
    for (const edge of workflow.transitions) {
      if (
        edge.condition.kind !== 'always' &&
        edge.condition.field &&
        rules.has(edge.condition.field) &&
        !rules.get(edge.condition.field)!.has(String(edge.condition.value))
      )
        return `Transition ${edge.id} uses an outcome its rule does not declare.`
    }
  }
  if (
    business.exceptions.some(
      (item) => item.resolution_state_id && !allStates.has(item.resolution_state_id),
    )
  )
    return 'An exception resolves to an unknown process step.'
  const affectable = new Set([
    ...requirementIds,
    ...roles.keys(),
    ...entities.keys(),
    ...rules.keys(),
    ...exceptionIds,
    ...business.decisions.map((item) => item.id),
    ...business.integrations.map((item) => item.id),
    ...business.terms.map((item) => item.id),
    ...allStates,
  ])
  if (business.decisions.some((item) => (item.affects ?? []).some((ref) => !affectable.has(ref))))
    return 'A decision affects an unknown item.'
  const checkTrace = (trace: Trace | undefined): string | null => {
    if (!trace) return null
    if (trace.workflow_id && !workflows.has(trace.workflow_id))
      return 'A trace refers to an unknown process.'
    if (trace.step_id && !workflows.get(trace.workflow_id!)?.has(trace.step_id))
      return 'A trace refers to an unknown process step.'
    if ((trace.requirement_ids ?? []).some((ref) => !requirementIds.has(ref)))
      return 'A trace refers to an unknown requirement.'
    if (
      trace.entity_id &&
      (!entities.has(trace.entity_id) ||
        (trace.attribute_id && !entities.get(trace.entity_id)!.has(trace.attribute_id)))
    )
      return 'A trace refers to an unknown entity or attribute.'
    if (
      trace.relationship_id &&
      !business.entities
        .find((item) => item.id === trace.entity_id)
        ?.relationships.some((item) => item.id === trace.relationship_id)
    )
      return 'A trace refers to an unknown relationship.'
    if (
      (trace.rule_id && !rules.has(trace.rule_id)) ||
      (trace.exception_id && !exceptionIds.has(trace.exception_id))
    )
      return 'A trace refers to an unknown rule or exception.'
    return null
  }
  type Traced = { trace?: Trace; children?: Traced[] }
  const visit = (nodes: Traced[]): string | null => {
    for (const node of nodes) {
      const error = checkTrace(node.trace) ?? visit(node.children ?? [])
      if (error) return error
    }
    return null
  }
  for (const screen of definition.screens) {
    const error = checkTrace(screen.trace) ?? visit(screen.components as Traced[])
    if (error) return error
  }
  return null
}

/** The next free ID with a readable prefix, unique across the whole business section. */
export function nextBusinessId(business: BusinessDefinition, prefix: string): string {
  const taken = new Set(
    [
      business.requirements,
      business.roles,
      business.entities,
      business.rules,
      business.exceptions,
      business.decisions,
      business.integrations,
      business.terms,
    ].flatMap((group) => group.map((item) => item.id)),
  )
  let n = 1
  while (taken.has(`${prefix}_${n}`)) n++
  return `${prefix}_${n}`
}

/** Readable ID from a name, made unique against `taken`. */
export function slugId(name: string, prefix: string, taken: Set<string>): string {
  const base =
    `${prefix}_${name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_|_$/g, '')}`
      .slice(0, 60)
      .replace(/_$/, '') || prefix
  let candidate = ID.test(base) ? base : `${prefix}_item`
  let n = 2
  while (taken.has(candidate)) candidate = `${base}_${n++}`
  return candidate
}

export const isBusinessAware = (definition: ApplicationDefinition) => {
  const business = definition.business
  return !!(
    definition.workflow_definitions?.length ||
    (business &&
      (business.requirements.length ||
        business.roles.length ||
        business.entities.length ||
        business.rules.length ||
        business.exceptions.length ||
        business.decisions.length ||
        business.integrations.length))
  )
}

type BusinessGroup =
  | 'requirements'
  | 'roles'
  | 'entities'
  | 'rules'
  | 'exceptions'
  | 'decisions'
  | 'integrations'
  | 'terms'

/** Remove one business item and every reference to it, so a removal never leaves a dangling link. */
export function removeBusinessItem(
  definition: ApplicationDefinition,
  group: BusinessGroup,
  itemId: string,
): ApplicationDefinition {
  const business = definition.business ?? emptyBusiness()
  const drop = (values: string[] | undefined) => (values ?? []).filter((value) => value !== itemId)
  const cleanTrace = (trace: Trace | undefined): Trace | undefined =>
    trace && {
      ...trace,
      requirement_ids: drop(trace.requirement_ids),
      ...(trace.entity_id === itemId
        ? { entity_id: null, attribute_id: null, relationship_id: null }
        : {}),
      ...(trace.rule_id === itemId ? { rule_id: null } : {}),
      ...(trace.exception_id === itemId ? { exception_id: null } : {}),
    }
  type Traced = { trace?: Trace; children?: Traced[] }
  const cleanNodes = <T extends Traced>(nodes: T[]): T[] =>
    nodes.map((node) => ({
      ...node,
      ...(node.trace ? { trace: cleanTrace(node.trace) } : {}),
      ...(node.children ? { children: cleanNodes(node.children) } : {}),
    }))
  return {
    ...definition,
    business: {
      ...business,
      [group]: (business[group] as { id: string }[]).filter((item) => item.id !== itemId),
      entities: business.entities
        .filter((item) => group !== 'entities' || item.id !== itemId)
        .map((item) => ({
          ...item,
          owner_role_id: item.owner_role_id === itemId ? null : item.owner_role_id,
          relationships: item.relationships.filter((relation) => relation.target !== itemId),
        })),
      integrations: business.integrations
        .filter((item) => group !== 'integrations' || item.id !== itemId)
        .map((item) => ({ ...item, entity_ids: drop(item.entity_ids) })),
      decisions: business.decisions
        .filter((item) => group !== 'decisions' || item.id !== itemId)
        .map((item) => ({ ...item, affects: drop(item.affects) })),
    },
    workflow_definitions: (definition.workflow_definitions ?? []).map((workflow) => ({
      ...workflow,
      states: workflow.states.map((state) => ({
        ...state,
        role_id: state.role_id === itemId ? null : state.role_id,
        permission: state.role_id === itemId ? null : state.permission,
        ...(state.input_fields
          ? {
              input_fields: Object.fromEntries(
                Object.entries(state.input_fields).filter(([entity]) => entity !== itemId),
              ),
            }
          : {}),
        ...(state.input_relationships
          ? {
              input_relationships: Object.fromEntries(
                Object.entries(state.input_relationships).filter(([entity]) => entity !== itemId),
              ),
            }
          : {}),
        requirement_ids: drop(state.requirement_ids),
        reads_entity_ids: drop(state.reads_entity_ids),
        writes_entity_ids: drop(state.writes_entity_ids),
        rule_ids: drop(state.rule_ids),
        exception_ids: drop(state.exception_ids),
        outputs: state.outputs.filter((output) => output !== itemId),
      })),
      transitions: workflow.transitions.map((edge) =>
        edge.condition.field === itemId
          ? { ...edge, condition: { kind: 'always' as const, field: null, value: null } }
          : edge,
      ),
    })),
    screens: definition.screens.map((screen) => ({
      ...screen,
      ...(screen.trace ? { trace: cleanTrace(screen.trace) } : {}),
      components: cleanNodes(screen.components),
    })),
  }
}

/** Who hands work to whom along the process: a role change across a transition. */
export function handoffs(definition: ApplicationDefinition) {
  const result: {
    workflow: string
    from: string
    to: string
    fromRole: string
    toRole: string
    permission: string | null
  }[] = []
  for (const workflow of definition.workflow_definitions ?? []) {
    const byId = new Map(workflow.states.map((state) => [state.id, state]))
    for (const edge of workflow.transitions) {
      const source = byId.get(edge.source),
        target = byId.get(edge.target)
      if (source?.role_id && target?.role_id && source.role_id !== target.role_id)
        result.push({
          workflow: workflow.name,
          from: source.label,
          to: target.label,
          fromRole: source.role_id,
          toRole: target.role_id,
          permission: target.permission ?? null,
        })
    }
  }
  return result
}

/** After process steps are removed, screens and components that traced them become unlinked manual items instead
 * of leaving dangling references (which validation would reject, blocking the removal). */
export function unlinkRemovedSteps(
  next: ApplicationDefinition,
  previous: ApplicationDefinition,
): ApplicationDefinition {
  const remaining = new Set(
    (next.workflow_definitions ?? []).flatMap((workflow) =>
      workflow.states.map((state) => `${workflow.id}/${state.id}`),
    ),
  )
  const removed = (previous.workflow_definitions ?? [])
    .flatMap((workflow) => workflow.states.map((state) => `${workflow.id}/${state.id}`))
    .filter((ref) => !remaining.has(ref))
  const remainingWorkflows = new Set(
    (next.workflow_definitions ?? []).map((workflow) => workflow.id),
  )
  if (
    !removed.length &&
    (previous.workflow_definitions ?? []).every((workflow) => remainingWorkflows.has(workflow.id))
  )
    return next
  const gone = (trace: Trace | undefined) =>
    !!trace &&
    ((trace.workflow_id && !remainingWorkflows.has(trace.workflow_id)) ||
      (trace.step_id && removed.includes(`${trace.workflow_id}/${trace.step_id}`)))
  type Traced = { trace?: Trace; children?: Traced[] }
  const clean = <T extends Traced>(nodes: T[]): T[] =>
    nodes.map((node) => {
      const copy = { ...node, ...(node.children ? { children: clean(node.children) } : {}) }
      if (gone(copy.trace)) delete copy.trace
      return copy
    })
  return {
    ...next,
    screens: next.screens.map((screen) => {
      const copy = { ...screen, components: clean(screen.components) }
      if (gone(copy.trace)) delete copy.trace
      return copy
    }),
  }
}
