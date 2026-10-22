/* Generated application client. All mutations use the same-origin runtime API; the server decides every permission.
   Every screen is derived from the specification (schema.json): a page per process, a list and form per record type, a work queue per role.
   In the Studio preview the same client runs without a server: records stay in this page's memory and processes do not run. */
const root = document.getElementById('app')
let application, instances = [], route = { page: 'home' }
const cache = new Map()
const closedGroups = new Set() // menu groups the person collapsed, kept across pages
const bootstrap = JSON.parse(document.getElementById('studio-bootstrap')?.textContent || '{"mode":"runtime"}')
const preview = bootstrap.mode === 'preview'
const PREVIEW_PROCESS = 'Run the application to execute its server-validated process. This preview keeps record changes in memory only.'

/* The Studio preview's stand-in for the runtime API: the same responses, no persistence, no process execution. */
const previewRole = preview ? bootstrap.preview_role || Object.keys(bootstrap.app?.roles || {})[0] : null
// The preview opens with illustrative sample records and cases (runtime_samples.py), so it does not look empty. They live in this page only.
const previewState = { user: previewRole ? { id: previewRole, role: previewRole, tenant: 'preview' } : null, records: structuredClone(bootstrap.samples?.records ?? {}) }
function previewInstances(view) {
  const role = previewState.user.role, permissions = bootstrap.app.role_permissions?.[role] ?? []
  return (bootstrap.samples?.instances ?? []).flatMap(sample => {
    const step = view.workflows.find(w => w.id === sample.workflow)?.states.find(s => s.id === sample.state)
    return step ? [{ id: sample.id, workflow: sample.workflow, state: sample.state, step, revision: 1, links: sample.links, can_act: step.kind !== 'end' && step.role_id === role && !!step.permission && permissions.includes(step.permission) }] : []
  })
}
function previewView() {
  const app = bootstrap.app, role = previewState.user?.role
  const permissions = app.role_permissions?.[role] ?? []
  const permits = step => step.role_id === role && step.permission && permissions.includes(step.permission)
  const steps = app.workflows.flatMap(workflow => workflow.states).filter(permits)
  const entities = app.entities.flatMap(entity => {
    const owner = entity.owner_role_id === role
    const writable = owner || steps.some(step => (step.writes_entity_ids ?? []).includes(entity.id))
    const readable = writable || steps.some(step => (step.reads_entity_ids ?? []).includes(entity.id))
    return readable ? [{ ...entity, writable, creatable: writable && (!entity.owner_role_id || owner) }] : []
  })
  const entity_names = Object.fromEntries(app.entities.map(entity => [entity.id, entity.name]))
  return { ...app, user: previewState.user, entities, entity_names, workflows: app.workflows.filter(workflow => workflow.states.some(permits)) }
}
function previewApi(path, body) {
  const app = bootstrap.app
  const fail = (status, message) => { const error = new Error(message); error.status = status; throw error }
  if (path === '/demo-users') return Object.entries(app.roles).map(([role, name]) => ({ id: role, name: name + ' · preview', tenant: 'preview', role, primary: app.workflows.some(w => w.states.some(s => s.role_id === role)) }))
  if (path === '/login') {
    if (!Object.hasOwn(app.roles, body?.user_id)) fail(401, 'Choose one of the listed preview roles.')
    previewState.user = { id: body.user_id, role: body.user_id, tenant: 'preview' }; return { signed_in: true }
  }
  if (!previewState.user) fail(401, 'Choose who you are working as.')
  const view = previewView()
  if (path === '/application') return view
  if (path === '/instances' && body === undefined) return previewInstances(view)
  const history = path.match(/^\/instances\/([^/]+)\/history$/)
  if (history && body === undefined) return (bootstrap.samples?.instances ?? []).find(i => i.id === history[1])?.events ?? []
  if (path.startsWith('/instances')) fail(409, PREVIEW_PROCESS)
  const [, , entityId, recordId] = path.split('/')
  const entity = view.entities.find(e => e.id === entityId)
  if (!entity) fail(403, 'Your role cannot access this record type.')
  const rows = previewState.records[entityId] ??= []
  if (body === undefined) return rows.map(row => ({ ...row, data: { ...row.data } }))
  if (!entity.writable || (!recordId && !entity.creatable)) fail(403, 'Your role cannot change this record.')
  for (const attr of entity.attributes) {
    if (body.data[attr.id] === undefined) continue
    if (attr.value_source && attr.value_source !== 'user_entered' || attr.writable === false)
      fail(422, attr.name + ' is set automatically.')
    if (attr.owner_role_id && attr.owner_role_id !== previewState.user.role)
      fail(403, attr.name + ' is maintained by another role.')
  }
  const missing = entity.attributes.filter(a => a.required && !a.allow_unknown && !a.system_managed && (a.value_source ?? 'user_entered') === 'user_entered' && (body.data[a.id] === undefined || body.data[a.id] === ''))
  if (!recordId && missing.length) fail(422, 'Required: ' + missing.map(a => a.name).join(', '))
  if (!recordId) {
    const row = { id: 'preview-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), revision: 1, data: { ...body.data } }
    // System-generated keys as the server assigns them (runtime_server.generated_value): the next number, or the record's own id.
    for (const a of entity.attributes.filter(a => a.value_source === 'system_generated' && row.data[a.id] == null))
      row.data[a.id] = a.type === 'integer' ? 1 + Math.max(0, ...rows.map(r => r.data[a.id]).filter(Number.isInteger)) : row.id
    rows.push(row); return row
  }
  const row = rows.find(r => r.id === recordId)
  if (!row) fail(404, 'Record not found.')
  if (row.revision !== body.expected_revision) fail(409, 'Someone changed this record since you opened it.')
  Object.assign(row.data, body.data); row.revision += 1
  return row
}

/* How this application presents itself. Decided by the generator from the specification (schema.json "presentation"). */
const PROFILES = {
  operations: { home: 'Control tower', homeIntro: 'Live work across your processes: what is moving, what is stuck and what needs you now.', tasks: 'My work queue', icon: '◧' },
  service: { home: 'Service desk', homeIntro: 'Open cases by stage, and the ones waiting for you.', tasks: 'My queue', icon: '◎' },
  requests: { home: 'My requests', homeIntro: 'Requests you started and approvals waiting for you.', tasks: 'Waiting for my approval', icon: '◇' },
  workspace: { home: 'Overview', homeIntro: 'Start with the next action, or open the records behind a process.', tasks: 'My tasks', icon: '▣' },
}
const profile = () => PROFILES[application?.presentation?.archetype] ?? PROFILES.workspace

function el(tag, text, attributes = {}) {
  const node = document.createElement(tag)
  if (text !== null && text !== undefined) node.textContent = text
  for (const [key, value] of Object.entries(attributes)) if (value !== undefined && value !== null && value !== false) node.setAttribute(key, value)
  return node
}
function append(parent, ...children) { for (const child of children) if (child) parent.append(child); return parent }
function button(text, action, className = '', label) {
  const node = el('button', text, { type: 'button', class: className, 'aria-label': label })
  node.addEventListener('click', async event => {
    event.stopPropagation()
    node.disabled = true
    try { await action() } catch (error) { notify(error.message, true) } finally { node.disabled = false }
  })
  return node
}
async function api(path, body) {
  if (preview) return previewApi(path, body)
  let response
  try { response = await fetch('/api' + path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) }
  catch { throw new Error('The application server is unavailable. Your input is kept; retry when it is running.') }
  const data = await response.json().catch(() => ({ error: 'Unexpected response from the server' }))
  if (!response.ok) { const error = new Error(data.error + (data.details ? ': ' + data.details.map(item => item.message).join(' ') : '')); error.status = response.status; throw error }
  return data
}
function notify(text, error = false) {
  const area = document.getElementById('notification')
  if (!area) return
  area.textContent = text
  area.setAttribute('role', error ? 'alert' : 'status')
  area.className = error ? 'notice error' : 'notice success'
  if (!error) setTimeout(() => { if (area.textContent === text) { area.textContent = ''; area.className = 'notice' } }, 6000)
}
async function records(entity) {
  if (!cache.has(entity)) cache.set(entity, await api('/records/' + entity))
  return cache.get(entity)
}
function labelled(text, input, hint) {
  const label = el('label', text)
  append(label, input, hint ? el('small', hint) : null)
  return label
}
const roleName = id => (id && application.roles?.[id]) || (id ? id.replace(/^role_/, '').replaceAll('_', ' ') : 'nobody yet')
const time = iso => { const date = new Date(iso); return isNaN(date) ? iso : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) }
const workflowOf = instance => application.workflows.find(w => w.id === instance.workflow)
const stateLabel = (workflow, id) => workflow?.states.find(s => s.id === id)?.label ?? id

/* Steps in the order work reaches them (breadth-first from the start); exceptions after the main flow. */
function ordered(workflow) {
  const start = workflow.states.find(s => s.kind === 'start')
  const seen = new Set(start ? [start.id] : []), order = start ? [start] : [], queue = start ? [start.id] : []
  while (queue.length) {
    const current = queue.shift()
    for (const edge of workflow.transitions.filter(e => e.source === current)) {
      if (seen.has(edge.target)) continue
      seen.add(edge.target); queue.push(edge.target); order.push(workflow.states.find(s => s.id === edge.target))
    }
  }
  const rest = workflow.states.filter(s => !seen.has(s.id))
  const main = [...order, ...rest].filter(Boolean)
  return [...main.filter(s => s.kind !== 'exception'), ...main.filter(s => s.kind === 'exception')]
}
/* The steps where work waits, in flow order (not automatic decisions, not the start). */
const columnsOf = workflow => ordered(workflow).filter(s => s.kind !== 'start' && s.kind !== 'branch')
function statusOf(instance) {
  if (instance.step.kind === 'end') return { text: instance.step.outcome === 'success' || !instance.step.outcome ? 'Completed' : instance.step.outcome === 'cancelled' ? 'Cancelled' : 'Closed', tone: instance.step.outcome && instance.step.outcome !== 'success' ? 'muted' : 'done' }
  if (instance.step.kind === 'exception') return { text: 'Exception', tone: 'danger' }
  if (instance.can_act) return { text: 'Your action', tone: 'action' }
  return { text: 'With ' + roleName(instance.step.role_id), tone: 'waiting' }
}
function pill(text, tone) { return el('span', text, { class: 'pill pill--' + tone }) }
function linkSummary(instance) {
  const parts = []
  for (const [entityId, recordId] of Object.entries(instance.links || {})) {
    const entity = application.entities.find(e => e.id === entityId)
    const row = cache.get(entityId)?.find(r => r.id === recordId)
    parts.push((entity?.name || entityId) + ' ' + (row ? recordLabel(entity, row) : recordId.slice(0, 6)))
  }
  return parts.join(' · ') || 'No records linked yet'
}

/* ── structure, derived from the specification ────────────────────────────
   Areas come from the knowledge each process was built from (presentation.areas). A record a process step writes is a document of
   that process; a record that must point at a document is one of its lines and lives inside it; everything else is reference data. */
const stepsOf = workflow => workflow.states.filter(s => !['start', 'end', 'branch'].includes(s.kind))
const writers = entityId => application.workflows.filter(w => w.states.some(s => (s.writes_entity_ids || []).includes(entityId)))
// Records that many other record types point at (items, places) are shared reference data, even when a step updates them.
const isShared = entity => new Set(application.references.filter(r => r.target === entity.id && r.source !== entity.id).map(r => r.source)).size >= 3
const isDocument = entity => writers(entity.id).length > 0 && !isShared(entity)
function parentOf(entity) {
  const ref = application.references.find(r => r.source === entity.id && r.required && r.target !== entity.id && isDocument(application.entities.find(e => e.id === r.target) || { id: '' }))
  return ref ? application.entities.find(e => e.id === ref.target) : null
}
function areas() {
  const visible = new Set(application.workflows.map(w => w.id))
  const declared = (application.presentation?.areas || []).map(a => ({ ...a, workflows: a.workflow_ids.filter(id => visible.has(id)).map(id => application.workflows.find(w => w.id === id)) })).filter(a => a.workflows.length)
  const placed = new Set(declared.flatMap(a => a.workflows.map(w => w.id)))
  const rest = application.workflows.filter(w => !placed.has(w.id) && !isView(w)), views = application.workflows.filter(w => !placed.has(w.id) && isView(w))
  return [...declared, ...(rest.length ? [{ id: 'other', name: declared.length ? 'Other processes' : 'Processes', workflows: rest }] : []), ...(views.length ? [{ id: 'views', name: 'Dashboards and views', workflows: views }] : [])]
}
// A dashboard, directory or tracking view is looked at, not started: every step of it only looks something up or checks it.
const isView = workflow => { const steps = workflow.states.filter(s => s.kind !== 'start' && s.kind !== 'end'); return steps.length > 0 && steps.every(s => s.kind === 'search' || s.kind === 'review') }
const areaOfWorkflow = workflow => areas().find(a => a.workflows.includes(workflow))
const areaOfEntity = entity => isDocument(entity) ? areaOfWorkflow(writers(entity.id)[0])?.name : 'Reference data'
const referenceData = () => application.entities.filter(e => !isDocument(e) && !parentOf(e))
const firstStep = workflow => { const start = workflow.states.find(s => s.kind === 'start'); const edge = workflow.transitions.find(e => e.source === start?.id); return workflow.states.find(s => s.id === edge?.target) }
const KIND = { form: 'Enter', action: 'Do', review: 'Check', approval: 'Approve', search: 'Look up', exception: 'Needs attention' }
const entityName = id => application.entities.find(e => e.id === id)?.name || application.entity_names?.[id] || 'a record you cannot open'

/* ── sign in ─────────────────────────────────────────────────────────── */
async function signIn() {
  root.replaceChildren()
  const users = await api('/demo-users')
  const card = el('section', null, { class: 'login' })
  append(card, el('p', 'LOCAL APPLICATION', { class: 'eyebrow' }), el('h1', 'Who are you working as?'),
    el('p', 'Choose a demonstration identity. Each one is a role in one organization; the server decides what that role may see and do.', { class: 'muted' }))
  const list = el('ul', null, { class: 'identities', 'aria-label': 'Demonstration identities' })
  // Roles that perform process steps first; a role with no steps only sees the shared pages, so it says so.
  for (const user of [...users].sort((a, b) => (b.primary !== false) - (a.primary !== false))) {
    const role = user.name.split(' · ')[0], organization = user.tenant.replace('demo_', '').replaceAll('_', ' ')
    const item = button('', async () => { await api('/login', { user_id: user.id }); await load() }, 'identity', `Sign in as ${role}, ${organization}`)
    append(item, el('strong', role), el('span', user.primary === false ? 'No process steps yet' : organization))
    list.append(append(el('li'), item))
  }
  append(card, list, el('p', 'Synthetic local identities only. Production identity is not connected.', { class: 'muted small' }), el('p', '', { id: 'notification', class: 'notice' }))
  root.append(card)
}

async function load() {
  cache.clear()
  application = await api('/application')
  instances = await api('/instances')
  const presentation = application.presentation || {}
  document.body.dataset.archetype = presentation.archetype || 'workspace'
  // The selected template is the visual layer only: design tokens, navigation style and density. Screens still come from the specification.
  for (const [name, value] of Object.entries(presentation.tokens || {})) document.body.style.setProperty(name, value)
  document.body.dataset.nav = presentation.navigation || 'sidebar'
  document.body.dataset.density = presentation.density || 'comfortable'
  if (presentation.touch) document.body.dataset.touch = 'true'
  document.title = application.name
  // Linked record names are shown on cards; load the ones this role can read, quietly.
  await Promise.all([...new Set(instances.flatMap(i => Object.keys(i.links || {})))].map(id => records(id).catch(() => [])))
  route = { page: 'home' }
  await render()
}
async function go(next) { route = next; await render(); document.querySelector('main')?.focus() }

/* ── shell ───────────────────────────────────────────────────────────── */
async function render() {
  root.replaceChildren()
  const shell = el('div', null, { class: 'shell' }), rail = el('aside', null, { class: 'rail' }), content = el('main', null, { tabindex: '-1' })
  const brand = el('div', null, { class: 'brand' })
  append(brand, el('span', profile().icon, { class: 'brand__mark', 'aria-hidden': 'true' }), append(el('div'), el('strong', application.name), el('small', application.user.tenant.replace('demo_', '').replaceAll('_', ' '))))
  const nav = el('nav', null, { 'aria-label': 'Application', id: 'application-navigation' })
  const menu = button('Menu', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true'
    menu.setAttribute('aria-expanded', String(open))
    rail.toggleAttribute('data-menu-open', open)
  }, 'mobile-menu', 'Application menu')
  menu.setAttribute('aria-expanded', 'false')
  menu.setAttribute('aria-controls', 'application-navigation')
  const entries = [] // what the Studio's screen explorer shows for this role; reported to the workspace in preview mode
  let section = ''
  const link = (target, label, count, into = nav) => {
    const active = route.page === target.page && (route.id ?? null) === (target.id ?? null)
    entries.push({ section, label, target, count: count || 0, active })
    const node = button('', () => go(target), active ? 'nav active' : 'nav')
    if (active) node.setAttribute('aria-current', 'page')
    append(node, el('span', label), count ? el('span', String(count), { class: 'count' }) : null)
    into.append(node)
  }
  const mine = instances.filter(i => i.can_act)
  link({ page: 'home' }, profile().home)
  link({ page: 'tasks' }, profile().tasks, mine.length)
  link({ page: 'reports' }, 'Reports')
  // One collapsible group per work area: its processes, then the documents this role's own steps fill in. A line of one of those
  // documents stays inside it; documents other roles fill in are reached from their process.
  const own = new Set(application.workflows.flatMap(w => w.states.filter(s => s.role_id === application.user.role).flatMap(s => s.writes_entity_ids || [])))
  const group = (id, title, count) => {
    const details = el('details', null, { class: 'nav-group', open: !closedGroups.has(id) })
    details.addEventListener('toggle', () => { if (details.open) closedGroups.delete(id); else closedGroups.add(id) })
    const items = el('div', null, { class: 'nav-group__items' })
    nav.append(append(details, append(el('summary'), el('span', title), el('span', String(count), { class: 'nav-group__count' })), items))
    return items
  }
  for (const area of areas()) {
    section = area.name
    const documents = application.entities.filter(e => own.has(e.id) && isDocument(e) && !own.has(parentOf(e)?.id) && areaOfWorkflow(writers(e.id)[0])?.id === area.id)
    const items = group('area:' + area.id, area.name, area.workflows.length + documents.length)
    for (const workflow of area.workflows) link({ page: 'workflow', id: workflow.id }, workflow.name, instances.filter(i => i.workflow === workflow.id && i.step.kind !== 'end').length, items)
    // A record that shares its name with a process of the group ("Warranty claim") would read as the same menu line twice.
    const processNames = new Set(area.workflows.map(w => w.name.trim().toLowerCase()))
    for (const entity of documents) link({ page: 'records', id: entity.id }, processNames.has(entity.name.trim().toLowerCase()) ? entity.name + ' records' : entity.name, null, items)
  }
  const reference = referenceData()
  section = 'Reference data'
  if (reference.length) {
    const items = group('reference', 'Reference data', reference.length)
    for (const entity of reference) link({ page: 'records', id: entity.id }, entity.name, null, items)
  }
  section = ''
  link({ page: 'catalog' }, 'All records')
  append(rail, brand, menu, nav, el('p', preview ? 'Studio preview · sample data, kept in this page only · processes run in the launched application' : 'Local application · isolated SQLite storage · no external integrations', { class: 'rail-footer' }))
  const header = el('header', null, { class: 'topbar' })
  append(header, el('span', application.presentation?.description || '', { class: 'topbar__about' }), preview ? pill('Preview', 'waiting') : null,
    append(el('span', null, { class: 'whoami' }), el('span', roleName(application.user.role), { class: 'whoami__role' }), el('span', application.user.tenant.replace('demo_', '').replaceAll('_', ' '))),
    button(preview ? 'Switch role' : 'Switch identity', signIn, 'ghost'))
  append(content, header, el('div', '', { id: 'notification', class: 'notice' }))
  const body = el('div', null, { class: 'page', 'aria-busy': 'true' })
  body.append(el('p', 'Loading…', { class: 'loading' }))
  append(content, body); append(shell, rail, content); root.append(shell)
  try {
    const view = el('div')
    if (route.page === 'home') await home(view)
    else if (route.page === 'tasks') await tasks(view)
    else if (route.page === 'reports') await reports(view)
    else if (route.page === 'workflow') await workflowPage(view, application.workflows.find(w => w.id === route.id))
    else if (route.page === 'instance') await instanceDetail(view, instances.find(i => i.id === route.id))
    else if (route.page === 'records') await entityPage(view, application.entities.find(e => e.id === route.id))
    else if (route.page === 'record') await recordForm(view, application.entities.find(e => e.id === route.entity), route.id)
    else if (route.page === 'catalog') await catalog(view)
    body.replaceChildren(...view.childNodes)
  } catch (error) {
    body.replaceChildren(el('div', error.message, { class: 'notice error', role: 'alert' }), button('Try again', render))
  } finally { body.removeAttribute('aria-busy'); announce(entries) }
}
/* Every record type this role may see, by the area that produces it; lines are listed under their document. */
async function catalog(body) {
  heading(body, roleName(application.user.role), 'All records', 'Documents by the area that produces them, with their lines, then the reference data they use.')
  const tile = async (entity, child = false) => {
    let count = '—'
    try { count = String((await records(entity.id)).length) } catch { /* not visible to this role */ }
    const node = button('', () => go({ page: 'records', id: entity.id }), child ? 'tile tile--child' : 'tile', 'Open ' + entity.name)
    return append(node, el('strong', entity.name), el('small', `${count} records${entity.description ? ' · ' + entity.description : ''}`))
  }
  const placed = new Set()
  const section = async (title, entities) => {
    if (!entities.length) return
    const grid = el('div', null, { class: 'catalog' })
    for (const entity of entities) {
      placed.add(entity.id); grid.append(await tile(entity))
      for (const line of application.entities.filter(e => parentOf(e)?.id === entity.id)) { placed.add(line.id); grid.append(await tile(line, true)) }
    }
    body.append(append(el('section', null, { class: 'card' }), el('h2', title), grid))
  }
  for (const area of areas()) {
    const ids = new Set(area.workflows.flatMap(w => stepsOf(w).flatMap(s => s.writes_entity_ids || [])))
    await section(area.name, application.entities.filter(e => ids.has(e.id) && isDocument(e) && !parentOf(e) && !placed.has(e.id)))
  }
  await section('Reference data', referenceData().filter(e => !placed.has(e.id)))
  await section('Other records', application.entities.filter(e => !placed.has(e.id)))
}
function heading(body, kicker, title, description, actions) {
  const head = el('div', null, { class: 'page-head' })
  append(head, append(el('div'), el('p', kicker, { class: 'eyebrow' }), el('h1', title), description ? el('p', description, { class: 'intro' }) : null), actions ? append(el('div', null, { class: 'page-head__actions' }), ...actions) : null)
  body.append(head)
}

/* ── home ────────────────────────────────────────────────────────────── */
async function home(body) {
  const p = profile()
  heading(body, roleName(application.user.role), p.home, p.homeIntro, startButtons())
  const open = instances.filter(i => i.step.kind !== 'end')
  const stats = el('div', null, { class: 'stats', role: 'list' })
  for (const [label, value, tone] of [['In progress', open.length, ''], [p.tasks, instances.filter(i => i.can_act).length, 'action'], ['Exceptions', open.filter(i => i.step.kind === 'exception').length, 'danger'], ['Completed', instances.filter(i => i.step.kind === 'end').length, 'done']]) {
    stats.append(append(el('article', null, { class: 'stat', role: 'listitem', 'data-tone': value ? tone : '' }), el('span', label), el('strong', String(value))))
  }
  body.append(stats)
  const grid = el('div', null, { class: 'home-grid' })
  const queue = append(el('section', null, { class: 'card' }), el('h2', p.tasks))
  const mine = instances.filter(i => i.can_act).slice(0, 6)
  if (!mine.length) queue.append(empty('Nothing is waiting for you.', application.workflows.some(canStart) ? 'Start a process from the button above.' : 'Work arrives here when a process reaches a step your role performs.'))
  for (const instance of mine) queue.append(instanceRow(instance))
  const flows = append(el('section', null, { class: 'card' }), el('h2', 'Where work is'))
  if (!application.workflows.length) flows.append(empty('No process is available to your role.'))
  for (const area of areas()) {
    if (areas().length > 1) flows.append(el('h3', area.name, { class: 'area-title' }))
    for (const workflow of area.workflows) flows.append(pipeline(workflow))
  }
  append(grid, queue, flows)
  body.append(grid)
  if (application.unsupported.length) body.append(gaps())
}
function canStart(workflow) {
  if (isView(workflow)) return false
  const start = workflow.states.find(s => s.kind === 'start')
  const first = workflow.transitions.find(e => e.source === start?.id)
  const step = workflow.states.find(s => s.id === first?.target)
  return step && step.role_id === application.user.role
}
function startButtons() {
  return application.workflows.filter(canStart).map(workflow => button('Start ' + workflow.name.toLowerCase(), async () => {
    const result = await api('/instances', { workflow_id: workflow.id, links: {} })
    instances = await api('/instances')
    await go({ page: 'instance', id: result.id })
    notify('Started. Link the records this step works on, then complete it.')
  }, 'primary'))
}
function pipeline(workflow) {
  const box = append(el('div', null, { class: 'pipeline' }), append(el('div', null, { class: 'pipeline__head' }), el('strong', workflow.name), button('Open board', () => go({ page: 'workflow', id: workflow.id }), 'link')))
  const list = el('ol')
  for (const step of columnsOf(workflow).filter(s => s.kind !== 'exception')) {
    const count = instances.filter(i => i.workflow === workflow.id && i.state === step.id).length
    list.append(append(el('li', null, { 'data-kind': step.kind, 'data-busy': count ? 'true' : undefined }), el('span', String(count), { class: 'pipeline__count' }), el('span', step.label)))
  }
  const stuck = instances.filter(i => i.workflow === workflow.id && i.step.kind === 'exception').length
  append(box, list, stuck ? el('p', `${stuck} in an exception path`, { class: 'pipeline__stuck' }) : null)
  return box
}
function empty(title, text) { return append(el('div', null, { class: 'empty' }), el('strong', title), text ? el('p', text) : null) }
function gaps() {
  const details = el('details', null, { class: 'gaps' })
  append(details, el('summary', `${application.unsupported.length} feature${application.unsupported.length === 1 ? ' is' : 's are'} not set up yet, so the actions that need ${application.unsupported.length === 1 ? 'it stay' : 'them stay'} switched off`))
  const list = el('ul'); for (const gap of application.unsupported) list.append(el('li', gap)); details.append(list)
  return details
}
function instanceRow(instance) {
  const workflow = workflowOf(instance), status = statusOf(instance)
  const row = button('', () => go({ page: 'instance', id: instance.id }), 'row', `Open ${workflow?.name}: ${instance.step.label}`)
  append(row, append(el('span', null, { class: 'row__main' }), el('strong', instance.step.label), el('small', `${workflow?.name ?? ''} · ${linkSummary(instance)}`)), pill(status.text, status.tone))
  return row
}

/* ── tasks and boards ────────────────────────────────────────────────── */
async function tasks(body) {
  heading(body, roleName(application.user.role), profile().tasks, 'Everything currently waiting on your role. The server re-checks your role, permission and the record revision on every action.', startButtons())
  const mine = instances.filter(i => i.can_act)
  if (!mine.length) body.append(empty('Nothing is waiting for you right now.'))
  const list = el('div', null, { class: 'card list' }); for (const instance of mine) list.append(instanceRow(instance)); if (mine.length) body.append(list)
  const others = instances.filter(i => !i.can_act && i.step.kind !== 'end')
  if (others.length) {
    body.append(el('h2', 'With someone else'))
    const rest = el('div', null, { class: 'card list' }); for (const instance of others.slice(0, 20)) rest.append(instanceRow(instance)); body.append(rest)
  }
}
/* A process page is a workspace shaped by the process itself: its first step's form, one lane per step with who does it, what it
   reads and changes and what is waiting there, lookups for search steps, approvals, exception paths and the documents it produces. */
async function workflowPage(body, workflow) {
  if (!workflow) return go({ page: 'home' })
  const mine = instances.filter(i => i.workflow === workflow.id)
  const first = firstStep(workflow), flow = columnsOf(workflow).filter(s => s.kind !== 'end')
  const steps = flow.filter(s => s.kind !== 'exception'), exceptions = flow.filter(s => s.kind === 'exception')
  const ends = workflow.states.filter(s => s.kind === 'end').map(s => s.label)
  heading(body, areaOfWorkflow(workflow)?.name || 'Process', workflow.name,
    [first?.role_id ? 'Started by ' + roleName(first.role_id) : null, `${steps.length} steps`, ends.length ? 'ends with ' + ends.join(' or ') : null].filter(Boolean).join(' · '))
  const open = mine.filter(i => i.step.kind !== 'end')
  const stats = el('div', null, { class: 'stats', role: 'list' })
  for (const [label, value, tone] of [['Open', open.length, ''], ['Waiting for you', open.filter(i => i.can_act).length, 'action'], ['Needs attention', open.filter(i => i.step.kind === 'exception').length, 'danger'], ['Finished', mine.length - open.length, 'done']])
    stats.append(append(el('article', null, { class: 'stat', role: 'listitem', 'data-tone': value ? tone : '' }), el('span', label), el('strong', String(value))))
  body.append(stats)
  if (canStart(workflow)) body.append(await startPanel(workflow, first))
  const attention = open.filter(i => i.step.kind === 'exception')
  if (attention.length) { const card = append(el('section', null, { class: 'card attention' }), el('h2', 'Needs attention')); for (const instance of attention) card.append(instanceRow(instance)); body.append(card) }
  const lanes = el('ol', null, { class: 'lanes', 'aria-label': 'Steps of ' + workflow.name })
  for (const [index, step] of steps.entries()) lanes.append(await lane(step, index + 1, mine.filter(i => i.state === step.id)))
  body.append(append(el('section', null, { class: 'workspace-steps' }), el('h2', 'Steps'), lanes))
  if (exceptions.length) {
    const card = append(el('section', null, { class: 'card' }), el('h2', 'When something goes wrong'))
    const list = el('ul', null, { class: 'exception-list' })
    for (const step of exceptions) list.append(append(el('li'), el('strong', step.label), el('span', `${roleName(step.role_id)} · ${mine.filter(i => i.state === step.id).length} waiting`, { class: 'muted' })))
    body.append(append(card, list))
  }
  const documents = [...new Set(stepsOf(workflow).flatMap(s => s.writes_entity_ids || []))].map(id => application.entities.find(e => e.id === id)).filter(e => e && isDocument(e) && !parentOf(e))
  if (documents.length) {
    const card = append(el('section', null, { class: 'card' }), el('h2', 'Records this process produces'))
    const chips = el('div', null, { class: 'chips' })
    for (const entity of documents) {
      let count = ''
      try { count = ` · ${(await records(entity.id)).length}` } catch { /* not visible to this role */ }
      chips.append(button(entity.name + count, () => go({ page: 'records', id: entity.id }), 'chip'))
    }
    body.append(append(card, chips))
  }
  const finished = mine.filter(i => i.step.kind === 'end').slice(-5).reverse()
  if (finished.length) { const card = append(el('section', null, { class: 'card list' }), el('h2', 'Recently finished')); for (const instance of finished) card.append(instanceRow(instance)); body.append(card) }
}
/* The first step, done right here: its record's form when the step writes one, otherwise a single start action. */
async function startPanel(workflow, first) {
  const entity = application.entities.find(e => (first?.writes_entity_ids || []).includes(e.id) && e.creatable && !parentOf(e))
  const card = append(el('section', null, { class: 'card start-panel' }), el('p', 'START', { class: 'eyebrow' }), el('h2', first?.label || 'Start'))
  if (!entity) return append(card, button('Start ' + workflow.name.toLowerCase(), () => startWorkflow(workflow, {}), 'primary'))
  card.append(el('p', `Saves the ${entity.name.toLowerCase()} and starts ${workflow.name.toLowerCase()}.`, { class: 'muted' }))
  const form = el('form', null, { class: 'record-form', novalidate: 'true' }), errors = el('div', null, { class: 'form-errors', role: 'alert' })
  form.append(errors)
  const fields = await editableFields(form, entity, null, null)
  const submit = el('button', first.label, { type: 'submit', class: 'primary' })
  form.append(append(el('div', null, { class: 'form-actions' }), submit))
  form.addEventListener('submit', async event => {
    event.preventDefault()
    errors.textContent = ''
    const { data, missing } = collectFields(fields)
    if (missing.length) { errors.textContent = 'Please fill in: ' + missing.join(', ') + '.'; return }
    submit.disabled = true
    try {
      const row = await api('/records/' + entity.id, { data })
      cache.delete(entity.id)
      await startWorkflow(workflow, { [entity.id]: row.id }, true, `${entity.name} saved.`)
    } catch (error) { errors.textContent = error.message } finally { submit.disabled = false }
  })
  return append(card, form)
}
/* Start the process with the records already chosen; when the first step's record was just entered, that step is done too. */
async function startWorkflow(workflow, links, completeFirst = false, saved = '') {
  let started
  try { started = await api('/instances', { workflow_id: workflow.id, links }) }
  catch (error) { await go({ page: 'workflow', id: workflow.id }); return notify(`${saved} ${error.message}`.trim(), !saved) }
  if (completeFirst) {
    try { await api(`/instances/${started.id}/advance`, { expected_revision: started.revision, links }) }
    catch (error) { instances = await api('/instances'); await go({ page: 'instance', id: started.id }); return notify(error.message, true) }
  }
  instances = await api('/instances')
  await go({ page: 'instance', id: started.id })
  notify(`${saved} Started ${workflow.name.toLowerCase()}.`.trim())
}
/* One step of a process: what it is, who does it, what it works on and what waits there. Search steps carry their lookup. */
async function lane(step, number, here) {
  const item = el('li', null, { class: 'lane', 'data-kind': step.kind })
  const reads = (step.reads_entity_ids || []).filter(id => !(step.writes_entity_ids || []).includes(id)), writes = step.writes_entity_ids || []
  append(item, append(el('div', null, { class: 'lane__head' }), el('span', String(number), { class: 'lane__number', 'aria-hidden': 'true' }),
    append(el('div'), el('strong', step.label), el('small', `${KIND[step.kind] || step.kind} · ${roleName(step.role_id)}`)),
    el('span', here.length ? `${here.length} waiting` : 'Nothing waiting', { class: 'pill pill--' + (here.some(i => i.can_act) ? 'action' : here.length ? 'waiting' : 'neutral') })))
  if (writes.length || reads.length) item.append(el('p', [writes.length ? 'Changes ' + writes.map(entityName).join(', ') : null, reads.length ? 'Uses ' + reads.map(entityName).join(', ') : null].filter(Boolean).join(' · '), { class: 'muted small' }))
  for (const instance of here) item.append(instanceRow(instance))
  if (step.kind === 'search' && reads.length) item.append(await lookup(application.entities.find(e => e.id === reads[0])))
  return item
}
/* A quick search over the records a search step looks at. */
async function lookup(entity) {
  if (!entity) return null
  let rows
  try { rows = await records(entity.id) } catch { return el('p', 'Your role cannot look up these records.', { class: 'muted small' }) }
  const box = el('div', null, { class: 'lookup' })
  const search = el('input', null, { type: 'search', placeholder: 'Find ' + entity.name.toLowerCase(), 'aria-label': 'Find ' + entity.name.toLowerCase() })
  const results = el('ul', null, { class: 'lookup__results' })
  const draw = () => {
    const query = search.value.toLowerCase()
    const shown = rows.filter(row => JSON.stringify(row.data).toLowerCase().includes(query)).slice(0, 5)
    results.replaceChildren(...(shown.length ? shown.map(row => append(el('li'), button(recordLabel(entity, row), () => go({ page: 'record', entity: entity.id, id: row.id }), 'link'))) : [el('li', rows.length ? 'No match.' : `No ${entity.name.toLowerCase()} records yet.`, { class: 'muted' })]))
  }
  search.addEventListener('input', draw); draw()
  return append(box, search, results)
}

/* ── one process instance ────────────────────────────────────────────── */
function conditionText(edge) {
  const c = edge.condition
  return c.kind === 'always' ? '' : ` when ${String(c.field).replaceAll('_', ' ')} ${c.kind === 'not_equals' ? 'is not' : 'is'} ${String(c.value).replaceAll('_', ' ').toLowerCase()}`
}
async function instanceDetail(body, instance) {
  if (!instance) return go({ page: 'home' })
  const workflow = workflowOf(instance), status = statusOf(instance)
  append(body, button('← ' + workflow.name, () => go({ page: 'workflow', id: workflow.id }), 'link back'))
  heading(body, workflow.name, instance.step.label, linkSummary(instance), [pill(status.text, status.tone)])
  const path = columnsOf(workflow).filter(s => s.kind !== 'exception')
  const reached = new Set()
  const history = await api(`/instances/${instance.id}/history`)
  for (const event of history) { if (event.data.state) reached.add(event.data.state); for (const hop of event.data.path || []) { reached.add(hop.source); reached.add(hop.target) } }
  const stepper = el('ol', null, { class: 'stepper', 'aria-label': 'Progress' })
  for (const step of path) stepper.append(append(el('li', null, { 'data-state': step.id === instance.state ? 'current' : reached.has(step.id) ? 'done' : 'todo', 'aria-current': step.id === instance.state ? 'step' : undefined }), el('span', step.label)))
  body.append(stepper)
  if (instance.step.kind === 'exception') body.append(el('div', 'This work is in an exception path: ' + instance.step.label + '. Resolve it to return to the main flow.', { class: 'notice error', role: 'status' }))

  const layout = el('div', null, { class: 'detail' })
  const action = append(el('section', null, { class: 'card action' }), el('h2', instance.step.kind === 'end' ? 'Finished' : instance.can_act ? 'Your action' : 'Waiting'))
  const links = {}
  const entityIds = [...new Set([...(instance.step.reads_entity_ids || []), ...(instance.step.writes_entity_ids || [])])]
  for (const entityId of entityIds) {
    const entity = application.entities.find(e => e.id === entityId)
    const select = el('select', null, { 'aria-label': 'Link ' + (entity?.name || entityId) })
    select.append(el('option', 'Select ' + (entity?.name || entityId).toLowerCase(), { value: '' }))
    try { for (const row of await records(entityId)) select.append(el('option', recordLabel(entity, row), { value: row.id })) }
    catch { select.append(el('option', 'Not visible to your role', { value: '' })) }
    select.value = instance.links[entityId] || ''
    select.disabled = !instance.can_act
    links[entityId] = select
    const writes = (instance.step.writes_entity_ids || []).includes(entityId)
    action.append(labelled(entity?.name || entityId, select, writes ? 'This step changes this record.' : 'This step reads this record.'))
  }
  if (instance.can_act) {
    action.append(button('Complete “' + instance.step.label + '”', async () => {
      const bindings = Object.fromEntries(Object.entries(links).filter(([, input]) => input.value).map(([key, input]) => [key, input.value]))
      await api(`/instances/${instance.id}/advance`, { expected_revision: instance.revision, links: bindings })
      instances = await api('/instances')
      const next = instances.find(i => i.id === instance.id)
      await go({ page: 'instance', id: instance.id })
      notify(next ? `Done. Now at “${next.step.label}”${next.can_act ? ' — also yours.' : ` with ${roleName(next.step.role_id)}.`}` : 'Done.')
    }, 'primary'))
  } else if (instance.step.kind !== 'end') action.append(el('p', `This step is performed by ${roleName(instance.step.role_id)}. Sign in as that role to continue it.`, { class: 'muted' }))
  const next = workflow.transitions.filter(edge => edge.source === instance.state)
  if (next.length) {
    const what = append(el('div', null, { class: 'next' }), el('h3', 'What happens next'))
    const list = el('ul'); for (const edge of next) list.append(el('li', stateLabel(workflow, edge.target) + conditionText(edge))); what.append(list)
    if ((instance.step.rule_ids || []).length) what.append(el('p', 'Business rules are evaluated by the server at this step; a rule without an executable binding stops the action instead of guessing.', { class: 'muted small' }))
    action.append(what)
  }
  const timeline = append(el('section', null, { class: 'card' }), el('h2', 'History'))
  const list = el('ol', null, { class: 'timeline' })
  for (const event of [...history].reverse()) {
    const who = event.actor.split(':').pop().replaceAll('_', ' ')
    const title = event.action === 'process.start' ? `Started at “${stateLabel(workflow, event.data.state)}”` : event.action === 'process.advance' ? (event.data.path || []).map(hop => `${stateLabel(workflow, hop.source)} → ${stateLabel(workflow, hop.target)}`).join(', ') : event.action
    const item = append(el('li'), el('strong', title), el('span', `${who} · ${time(event.at)}`))
    const outputs = Object.entries(event.data.outputs || {})
    if (outputs.length) item.append(el('small', 'Decided: ' + outputs.map(([key, value]) => `${key.replaceAll('_', ' ')} = ${value}`).join(', ')))
    list.append(item)
  }
  timeline.append(list)
  append(layout, action, timeline)
  body.append(layout)
}

/* ── reports ─────────────────────────────────────────────────────────── */
/* Counts from the application's own data only: work by process step, and records by their status values. No metric is invented. */
async function reports(body) {
  heading(body, roleName(application.user.role), 'Reports', 'Where work is in each process and how records stand, from the data this role can see.')
  const flows = append(el('section', null, { class: 'card' }), el('h2', 'Work by process step'))
  if (!application.workflows.length) flows.append(empty('No process is available to your role.'))
  for (const workflow of application.workflows) {
    const mine = instances.filter(i => i.workflow === workflow.id)
    const table = el('table', null, { 'aria-label': workflow.name }), head = el('tr'), counts = el('tr')
    for (const step of columnsOf(workflow)) { head.append(el('th', step.label, { scope: 'col' })); counts.append(el('td', String(mine.filter(i => i.state === step.id).length))) }
    append(flows, el('h3', `${workflow.name} · ${mine.filter(i => i.step.kind !== 'end').length} open, ${mine.filter(i => i.step.kind === 'end').length} finished`), append(el('div', null, { class: 'table-scroll' }), append(table, append(el('thead'), head), append(el('tbody'), counts))))
  }
  const recordsCard = append(el('section', null, { class: 'card' }), el('h2', 'Records by status'))
  const table = el('table', null, { 'aria-label': 'Records by status' })
  append(table, append(el('thead'), append(el('tr'), el('th', 'Record type', { scope: 'col' }), el('th', 'Total', { scope: 'col' }), el('th', 'By status', { scope: 'col' }))))
  const tbody = el('tbody'); table.append(tbody)
  for (const entity of [...application.entities].sort((a, b) => a.name.localeCompare(b.name))) {
    let rows
    try { rows = await records(entity.id) } catch { continue }
    const status = statusAttribute(entity)
    const by = status ? status.enum.map(value => `${value} ${rows.filter(r => r.data[status.id] === value).length}`).join(' · ') : '—'
    tbody.append(append(el('tr'), el('td', entity.name, { class: 'strong' }), el('td', String(rows.length)), el('td', by, { class: 'muted' })))
  }
  body.append(flows, append(recordsCard, append(el('div', null, { class: 'table-scroll' }), table)))
}

/* ── records ─────────────────────────────────────────────────────────── */
function recordLabel(entity, row) {
  const key = entity?.attributes.find(a => a.key)?.id
  const name = entity?.attributes.find(a => /name|title/i.test(a.id) && !a.key)?.id
  const value = row.data[key] ?? Object.values(row.data)[0] ?? row.id
  return name && row.data[name] ? `${value} · ${row.data[name]}` : String(value)
}
const statusAttribute = entity => entity.attributes.find(a => a.enum?.length && /status|state|stage/i.test(a.id + a.name)) || entity.attributes.find(a => a.enum?.length)
function format(attribute, value) {
  if (value === undefined || value === null || value === '') return '—'
  if (attribute.type === 'boolean') return value ? 'Yes' : 'No'
  if (attribute.type === 'datetime') return time(value)
  return String(value)
}
async function entityPage(body, entity) {
  if (!entity) return go({ page: 'home' })
  const parent = parentOf(entity)
  heading(body, parent ? 'Lines of ' + parent.name.toLowerCase() : areaOfEntity(entity), entity.name, entity.description || 'The records your processes work on.', entity.creatable ? [button('Add record', () => go({ page: 'record', entity: entity.id, id: 'new' }), 'primary', 'Add a record to ' + entity.name)] : [])
  let rows
  try { rows = await records(entity.id) } catch (error) { return body.append(el('div', error.status === 403 ? 'Your role cannot see these records.' : error.message, { class: 'notice error', role: 'alert' })) }
  const status = statusAttribute(entity)
  const toolbar = el('div', null, { class: 'toolbar' })
  const search = el('input', null, { type: 'search', placeholder: 'Search ' + entity.name.toLowerCase(), 'aria-label': 'Search records' })
  const filter = status ? el('select', null, { 'aria-label': 'Filter by ' + status.name }) : null
  if (filter) { filter.append(el('option', 'All ' + status.name.toLowerCase(), { value: '' })); for (const value of status.enum) filter.append(el('option', value, { value })) }
  const counter = el('span', '', { class: 'muted', role: 'status' })
  append(toolbar, search, filter, counter)
  body.append(toolbar)
  if (!rows.length) return body.append(empty('No records in ' + entity.name + ' yet.', entity.creatable ? 'Add the first one to get started.' : 'Records appear here when a role that may create them adds one.'))
  const columns = [...entity.attributes.filter(a => a.key), ...entity.attributes.filter(a => !a.key && a !== status)].slice(0, status ? 4 : 5)
  const table = el('table', null, { 'aria-label': entity.name + ' records' }), head = el('tr')
  for (const attribute of columns) head.append(el('th', attribute.name, { scope: 'col' }))
  if (status) head.append(el('th', status.name, { scope: 'col' }))
  append(table, append(el('thead'), head))
  const tbody = el('tbody'); table.append(tbody)
  const draw = () => {
    tbody.replaceChildren()
    const query = search.value.toLowerCase()
    const shown = rows.filter(row => JSON.stringify(row.data).toLowerCase().includes(query) && (!filter?.value || row.data[status.id] === filter.value))
    counter.textContent = `${shown.length} of ${rows.length}`
    for (const row of shown) {
      const tr = el('tr', null, { tabindex: '0', 'aria-label': 'Open ' + recordLabel(entity, row) })
      const open = () => go({ page: 'record', entity: entity.id, id: row.id })
      tr.addEventListener('click', open); tr.addEventListener('keydown', event => { if (event.key === 'Enter') open() })
      columns.forEach((attribute, index) => tr.append(el('td', format(attribute, row.data[attribute.id]), index === 0 ? { class: 'strong' } : {})))
      if (status) { const cell = el('td'); cell.append(pill(format(status, row.data[status.id]), 'neutral')); tr.append(cell) }
      tbody.append(tr)
    }
    if (!shown.length) { const tr = el('tr'); tr.append(el('td', 'No records match.', { colspan: String(columns.length + (status ? 1 : 0)), class: 'muted' })); tbody.append(tr) }
  }
  search.addEventListener('input', draw); filter?.addEventListener('change', draw); draw()
  body.append(append(el('div', null, { class: 'table-scroll card' }), table))
}
async function recordForm(body, entity, id) {
  if (!entity) return go({ page: 'home' })
  const rows = await records(entity.id)
  const row = id === 'new' ? null : rows.find(r => r.id === id)
  // A record added from its parent ("Add receipt line" on a goods receipt) returns to that parent.
  const back = route.back || { page: 'records', id: entity.id }
  const backName = route.back ? application.entities.find(e => e.id === route.back.entity)?.name || entity.name : entity.name
  append(body, button('← ' + backName, () => go(back), 'link back'))
  heading(body, entity.name, row ? recordLabel(entity, row) : 'New record', row ? `Revision ${row.revision}. Saving checks that nobody changed it since you opened it.` : 'Fields marked * are required. The server validates everything again.')
  const form = el('form', null, { class: 'card record-form', novalidate: 'true' })
  const errors = el('div', null, { class: 'form-errors', role: 'alert' })
  form.append(errors)
  const fields = await editableFields(form, entity, row, route.prefill)
  const actions = el('div', null, { class: 'form-actions' })
  const submit = el('button', row ? 'Save changes' : 'Create record', { type: 'submit', class: 'primary' }); submit.disabled = !entity.writable
  append(actions, submit, button('Cancel', () => go(back), 'ghost'), !entity.writable ? el('span', 'Your role can read these records but not change them.', { class: 'muted' }) : null)
  form.append(actions)
  form.addEventListener('submit', async event => {
    event.preventDefault()
    errors.textContent = ''
    const { data, missing } = collectFields(fields)
    if (missing.length) { errors.textContent = 'Please fill in: ' + missing.join(', ') + '.'; return }
    submit.disabled = true
    try {
      await api('/records/' + entity.id + (row ? '/' + row.id : ''), { data, ...(row ? { expected_revision: row.revision } : {}) })
      cache.delete(entity.id)
      await go(back)
      notify(row ? 'Changes saved.' : 'Record created in ' + entity.name + '.')
    } catch (error) { errors.textContent = error.status === 409 ? error.message + ' Reload to see the latest version.' : error.message }
    finally { submit.disabled = !entity.writable }
  })
  body.append(form)
  if (row) await relatedRecords(body, entity, row)
}

/* The editable fields of a record type, appended to a form: typed inputs, value lists, and selects for the records it points at. */
async function editableFields(form, entity, row, prefill) {
  const fields = new Map()
  const refs = application.references.filter(r => r.source === entity.id)
  // A link field is named after its relationship ("Goods receipt"), or the record it points at; never the internal relationship id.
  const linkName = r => entity.relationships?.find(x => x.id === r.relationship_id)?.name || entityName(r.target)
  const attributes = [...entity.attributes, ...refs.filter(r => r.enforcement === 'link').map(r => ({ id: r.field, name: linkName(r), type: 'string', required: r.required, writable: true }))]
  for (const attr of attributes) {
    if (attr.system_managed || attr.writable === false) continue
    const reference = refs.find(r => r.field === attr.id)
    let input
    if (reference || attr.enum?.length || attr.type === 'boolean') {
      input = el('select'); input.append(el('option', 'Choose…', { value: '' }))
      if (reference) {
        try { for (const item of await records(reference.target)) input.append(el('option', recordLabel(application.entities.find(e => e.id === reference.target), item), { value: reference.enforcement === 'foreign_key' ? item.data[reference.target_key] : item.id })) }
        catch { input.append(el('option', 'Related records are not visible to your role', { value: '' })) }
      } else for (const value of attr.type === 'boolean' ? ['true', 'false'] : attr.enum) input.append(el('option', attr.type === 'boolean' ? (value === 'true' ? 'Yes' : 'No') : value, { value }))
    } else {
      input = el('input', null, { type: ['integer', 'decimal'].includes(attr.type) ? 'number' : attr.type === 'date' ? 'date' : attr.type === 'datetime' ? 'datetime-local' : 'text' })
      if (attr.type === 'decimal') input.step = 'any'
      if (attr.minimum != null) input.min = String(attr.minimum)
      if (attr.maximum != null) input.max = String(attr.maximum)
      if (attr.min_length != null) input.minLength = attr.min_length
      if (attr.max_length != null) input.maxLength = attr.max_length
    }
    const initial = row ? row.data[attr.id] : prefill?.[attr.id]
    input.value = initial == null ? '' : String(initial)
    input.required = Boolean(attr.required && !attr.allow_unknown)
    input.disabled = !entity.writable || Boolean(row && attr.key) || Boolean(attr.owner_role_id && attr.owner_role_id !== application.user.role)
    input.setAttribute('aria-label', attr.name)
    fields.set(attr.id, { input, attr })
    const hint = attr.owner_role_id && attr.owner_role_id !== application.user.role ? `Only ${roleName(attr.owner_role_id)} may change this.` : row && attr.key ? 'Identifies the record; it cannot change.' : attr.description
    form.append(labelled(attr.name + (input.required ? ' *' : ''), input, hint))
  }
  return fields
}
function collectFields(fields) {
  const data = {}
  const missing = [...fields.values()].filter(({ input }) => input.required && !input.disabled && input.value === '').map(({ attr }) => attr.name)
  for (const [key, { input, attr }] of fields) {
    if (attr.owner_role_id && attr.owner_role_id !== application.user.role) continue
    if (input.value === '') continue
    data[key] = ['integer', 'decimal'].includes(attr.type) ? Number(input.value) : attr.type === 'boolean' ? input.value === 'true' : input.value
  }
  return { data, missing }
}

/* The records that point at this one (the lines of a goods receipt, the counts of a warehouse), from the relationships in the specification. */
async function relatedRecords(body, entity, row) {
  for (const ref of application.references.filter(r => r.target === entity.id)) {
    const child = application.entities.find(e => e.id === ref.source)
    if (!child) continue // not visible to this role
    const value = ref.enforcement === 'foreign_key' ? row.data[ref.target_key] : row.id
    let rows
    try { rows = (await records(child.id)).filter(item => item.data[ref.field] === value) } catch { continue }
    const section = append(el('section', null, { class: 'card related' }), append(el('div', null, { class: 'related__head' }),
      el('h2', `${child.name} (${rows.length})`),
      child.creatable && value != null ? button('Add ' + child.name.toLowerCase(), () => go({ page: 'record', entity: child.id, id: 'new', prefill: { [ref.field]: value }, back: { page: 'record', entity: entity.id, id: row.id } }), '', `Add ${child.name.toLowerCase()} to this ${entity.name.toLowerCase()}`) : null))
    if (!rows.length) section.append(el('p', `No ${child.name.toLowerCase()} records yet.`, { class: 'muted' }))
    const columns = child.attributes.filter(a => a.id !== ref.field).slice(0, 4)
    if (rows.length) {
      const table = el('table', null, { 'aria-label': child.name }), head = el('tr')
      for (const attribute of columns) head.append(el('th', attribute.name, { scope: 'col' }))
      const tbody = el('tbody')
      for (const item of rows) {
        const tr = el('tr', null, { tabindex: '0', 'aria-label': 'Open ' + recordLabel(child, item) })
        const open = () => go({ page: 'record', entity: child.id, id: item.id, back: { page: 'record', entity: entity.id, id: row.id } })
        tr.addEventListener('click', open); tr.addEventListener('keydown', event => { if (event.key === 'Enter') open() })
        for (const attribute of columns) tr.append(el('td', format(attribute, item.data[attribute.id])))
        tbody.append(tr)
      }
      section.append(append(el('div', null, { class: 'table-scroll' }), append(table, append(el('thead'), head), tbody)))
    }
    body.append(section)
  }
}

/* ── Studio bridge (preview only) ────────────────────────────────────────
   The workspace around the preview shows this role's menu, follows the current screen and can switch role or screen. Messages are
   plain data between the workspace and this sandboxed page; nothing here can reach a record or a server. */
const PAGES = new Set(['home', 'tasks', 'reports', 'workflow', 'records', 'record', 'catalog', 'instance'])
function announce(menu) {
  if (!preview || window.parent === window || !application) return
  const entry = menu.find(item => item.active)
  window.parent.postMessage({
    type: 'studio:state', role: application.user.role, roleName: roleName(application.user.role),
    route: { page: route.page, id: route.id ?? null, entity: route.entity ?? null },
    title: document.querySelector('main h1')?.textContent || entry?.label || '', menu,
  }, '*')
}
if (preview) window.addEventListener('message', async event => {
  const message = event.data
  if (event.source !== window.parent || !message || typeof message.type !== 'string') return
  if (message.type === 'studio:layout') { if (message.embedded) document.body.dataset.embedded = 'true'; else delete document.body.dataset.embedded; return }
  if (message.type !== 'studio:go') return
  try {
    if (typeof message.role === 'string' && message.role !== application?.user?.role) { await api('/login', { user_id: message.role }); await load() }
    const target = message.route
    if (target && PAGES.has(target.page)) await go({ page: target.page, ...(typeof target.id === 'string' ? { id: target.id } : {}), ...(typeof target.entity === 'string' ? { entity: target.entity } : {}) })
  } catch { /* a screen this role cannot open stays where it is */ }
})

load().catch(() => signIn()).catch(error => { root.replaceChildren(el('p', error.message, { role: 'alert' })) })
