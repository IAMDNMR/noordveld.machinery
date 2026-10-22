// Real browser journey against an exported runtime. No Studio preview or mocked APIs.
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'

const base = process.env.RUNTIME_URL || 'http://127.0.0.1:8091'
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base)) throw new Error('Loopback runtime required')
const output = process.env.RUNTIME_SCREENSHOTS || process.env.TEMP
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = [], requests = []
page.on('pageerror', error => errors.push(error.message))
page.on('request', request => { if (request.method() === 'POST') requests.push(new URL(request.url()).pathname) })
const suffix = String(Date.now()).slice(-8)
const carrier = 'C-' + suffix, vehicle = 'V-' + suffix, shipment = 'S-' + suffix
async function login(role, tenant = 'demo_noordveld') {
  if (await page.getByRole('button', { name: 'Switch demo identity' }).count()) await page.getByRole('button', { name: 'Switch demo identity' }).click()
  await page.getByLabel('Application identity').selectOption(`${tenant}:role_${role}`)
  await page.getByRole('button', { name: 'Open workspace' }).click()
  await page.getByRole('heading', { name: 'A clear view of your work' }).waitFor()
}
async function nav(name) { await page.getByRole('navigation').getByRole('button', { name, exact: true }).click() }
async function create(entity, fields) {
  await nav(entity)
  await page.getByRole('button', { name: 'Create ' + entity, exact: true }).click()
  for (const [name, value] of Object.entries(fields)) {
    const field = page.getByLabel(name, { exact: true })
    if (await field.evaluate(node => node.tagName) === 'SELECT') await field.selectOption(value)
    else await field.fill(String(value))
  }
  await page.getByRole('button', { name: 'Create record', exact: true }).click()
  await page.getByText('Record created and saved.', { exact: true }).waitFor()
}
async function editShipment(fields) {
  await nav('Shipments')
  await page.getByRole('button', { name: 'Open ' + shipment, exact: true }).click()
  for (const [name, value] of Object.entries(fields)) {
    const field = page.getByLabel(name, { exact: true })
    if (await field.evaluate(node => node.tagName) === 'SELECT') await field.selectOption(value)
    else await field.fill(String(value))
  }
  await page.getByRole('button', { name: 'Save changes', exact: true }).click()
  await page.getByText('Record updated.', { exact: true }).waitFor()
}
async function openProcess() {
  await nav('Processes & tasks')
  await page.getByRole('button', { name: 'Open process', exact: true }).first().click()
}
async function complete(next) {
  await page.getByRole('button', { name: 'Complete current task', exact: true }).click()
  await page.getByRole('heading', { name: next, exact: true }).waitFor()
}
try {
  await page.goto(base)
  await login('planner')
  await create('Carriers', { 'Carrier code': carrier, 'Carrier name': 'Synthetic Logistics', 'Eligible for this synthetic service': 'true' })
  await create('Vehicles', { 'Vehicle code': vehicle, 'Capacity (kg)': 1000 })
  await create('Shipments', { 'Shipment reference': shipment, Destination: 'Rotterdam test depot', 'Load weight (kg)': 500, Carrier: carrier, Vehicle: vehicle, Route: 'Synthetic route A' })
  await page.reload()
  await nav('Shipments')
  await page.getByRole('button', { name: 'Open ' + shipment, exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Open ' + shipment, exact: true }).count(), 1, 'Record survives browser reload')
  await nav('Processes & tasks')
  await page.getByRole('button', { name: 'Start process', exact: true }).click()
  await page.getByLabel('Link Shipments', { exact: true }).selectOption({ label: shipment })
  await complete('Plan route and assign carrier / vehicle')
  await page.getByLabel('Link Carriers', { exact: true }).selectOption({ label: carrier })
  await page.getByLabel('Link Vehicles', { exact: true }).selectOption({ label: vehicle })
  await complete('Release warehouse handoff')
  assert.equal(await page.getByRole('button', { name: 'Complete current task' }).isDisabled(), true)
  await login('warehouse')
  await openProcess()
  await page.getByRole('button', { name: 'Complete current task', exact: true }).click()
  await page.getByRole('alert').waitFor()
  assert.match(await page.getByRole('alert').innerText(), /Missing prerequisite|Warehouse release/)
  await editShipment({ 'Warehouse released': 'true' })
  await openProcess(); await complete('Dispatch shipment')
  await login('dispatcher')
  await openProcess(); await complete('Record tracking update')
  await editShipment({ 'Tracking status': 'DELAYED' })
  await openProcess(); await complete('Resolve delivery exception')
  await editShipment({ 'Exception resolution': 'RETRY' })
  await openProcess(); await complete('Record tracking update')
  await editShipment({ 'Tracking status': 'DELIVERED' })
  await openProcess(); await complete('Confirm delivery and proof')
  await login('carrier')
  await openProcess()
  await page.getByRole('button', { name: 'Complete current task', exact: true }).click()
  await page.getByRole('alert').waitFor()
  assert.match(await page.getByRole('alert').innerText(), /Missing prerequisite/)
  await editShipment({ 'Received by': 'Synthetic Recipient', 'Proof of delivery reference': 'POD-' + suffix })
  await openProcess(); await complete('Delivered with proof')
  await page.screenshot({ path: join(output, 'generated-runtime-delivered.png'), fullPage: true })
  await nav('Overview')
  await page.screenshot({ path: join(output, 'generated-runtime-dashboard.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await nav('Shipments')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'No page overflow at mobile width')
  await page.screenshot({ path: join(output, 'generated-runtime-mobile.png'), fullPage: true })
  await login('planner', 'demo_harbor')
  await nav('Shipments')
  await page.getByText('No records yet. Create the first record to get started.', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Open ' + shipment, exact: true }).count(), 0)
  assert.deepEqual(errors, [])
  assert(requests.some(path => path.endsWith('/advance')))
  console.log(JSON.stringify({ status: 'passed', journey: 'create → reload → plan/assign → warehouse prerequisite → dispatch → delayed → retry → delivery → POD prerequisite → completed → tenant isolation', posts: requests.length, pageErrors: errors.length, screenshots: output }))
} finally { await browser.close() }
