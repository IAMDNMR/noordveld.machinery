// End-to-end journey for the voice-first Design Studio, in a real browser against the isolated local Studio (never a deployed one):
//   speak a request (a recorded sentence is the microphone) -> real speech-to-text -> the assistant's plan -> review and apply -> answer open decisions
//   -> a separate approver approves -> screens -> design approval -> generate -> run its tests -> launch it and call it.
// Needs: the local Studio API and the Vite dev server (see backend/DESIGN_STUDIO_ACTIVATION.md), STUDIO_WAV_REQUEST and STUDIO_WAV_APPLY (16 kHz WAV files of
// "I want to build a transport management system ..." and "Go ahead and apply the change."), and optionally STUDIO_SHOTS (a directory for screenshots).
import { chromium } from 'playwright-core'
import assert from 'node:assert/strict'

const base = process.env.STUDIO_URL || 'http://127.0.0.1:5193'
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base)) throw new Error('A loopback Studio is required')
const wavRequest = process.env.STUDIO_WAV_REQUEST
const wavApply = process.env.STUDIO_WAV_APPLY
const shots = process.env.STUDIO_SHOTS
const log = (...parts) => console.log('•', ...parts)
const launch = wav => chromium.launch({ channel: 'msedge', headless: true, args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required', ...(wav ? [`--use-file-for-fake-audio-capture=${wav}%noloop`] : [])] })
const signIn = async (context, user) => { const r = await context.request.post(base + '/api/v1/auth/login', { data: { user_id: user } }); assert.equal(r.status(), 200) }
const shot = async (page, name) => { if (shots) await page.screenshot({ path: `${shots}/${name}.png` }) }
const errors = []
const watch = page => { page.on('pageerror', error => errors.push(error.message)); page.on('console', message => { if (message.type() === 'error' && !/401|Failed to load resource/.test(message.text())) errors.push(message.text()) }) }
const stage = (page, label) => page.getByRole('navigation', { name: 'Application stages' }).getByRole('button', { name: new RegExp(label) }).click()
const thread = page => page.getByRole('log', { name: 'Conversation' })

let page, bob
process.on('uncaughtException', async error => { console.error(String(error.message).split(String.fromCharCode(10))[0]); for (const [name, target] of [['alice', page], ['bob', bob]]) { try { if (target) await target.screenshot({ path: `${shots || '.'}/FAIL-${name}.png` }) } catch { /* the page may already be closed */ } } process.exit(1) })

// ── 1. Alice speaks the request ──
let browser = await launch(wavRequest)
let context = await browser.newContext({ viewport: { width: 1440, height: 900 }, permissions: ['microphone'] })
await signIn(context, 'studio-alice')
page = await context.newPage(); watch(page)
await page.goto(base + '/design-studio')
const status = await (await context.request.get(base + '/api/v1/design-studio/voice/status')).json()
log('voice status:', status.speech.enabled ? 'speech ready (' + status.speech.provider + ')' : 'speech unavailable: ' + status.speech.reason, '| model:', status.assistant.enabled ? status.assistant.provider : 'none')
await page.getByRole('heading', { name: 'What would you like to build?' }).waitFor()
await shot(page, '01-hero')
if (wavRequest && status.speech.enabled) {
  await page.getByRole('button', { name: 'Start talking' }).click()
  await page.getByText('Listening…').first().waitFor({ timeout: 10000 })
  await shot(page, '02-listening')
  log('listening; the recorded sentence is playing as the microphone')
  await page.getByText('Transcribing…').first().waitFor({ timeout: 40000 })
  log('transcribing through the server')
} else {
  await page.getByLabel('Describe the application you want to build').fill('I want to build a transport management system for our company to manage transport requests, vehicle assignments, shipment tracking, deliveries, and exceptions.')
  await page.getByRole('button', { name: 'Start building' }).click()
}
await page.waitForURL(/\/design-studio\/app_/, { timeout: 90000 })
const spoken = thread(page).locator('.sw-msg--user').first()
await spoken.waitFor({ timeout: 30000 })
const heard = (await spoken.innerText()).toLowerCase()
log('transcript shown:', heard.slice(0, 90) + '…')
assert.match(heard, /transport management system/)
const proposal = page.getByRole('region', { name: 'Proposed change' }).first()
await proposal.waitFor({ timeout: 90000 })
await shot(page, '03-first-reply')
const reply = await thread(page).locator('.sw-msg--assistant > p').first().innerText()
log('assistant:', reply.slice(0, 160))
if (wavRequest && status.speech.enabled) {
  const spoke = await page.getByText('Speaking').first().isVisible().catch(() => false)
  log('assistant spoke the reply aloud:', spoke ? 'yes (seen)' : 'finished before it could be observed')
  const stop = page.getByRole('button', { name: 'Stop speaking' })
  if (await stop.isVisible().catch(() => false)) {
    await stop.click()
    await page.locator('.sw-voicebar').getByText('Ready').waitFor({ timeout: 5000 })
    log('interrupted the spoken reply; the assistant went quiet at once')
  }
}
assert.match(await proposal.innerText(), /noordveld_transport|Reference knowledge/i)
assert.equal(await page.getByRole('button', { name: /Domain Knowledge/ }).count() > 0, true)
const projectUrl = page.url().split('?')[0]
const storage = await context.storageState()
await browser.close()

// ── 2. Alice says "Go ahead and apply the change." (a second recording), while the proposal is waiting on screen ──
browser = await launch(wavApply)
context = await browser.newContext({ viewport: { width: 1440, height: 900 }, permissions: ['microphone'], storageState: storage })
page = await context.newPage(); watch(page)
await page.goto(projectUrl)
await page.getByRole('region', { name: 'Proposed change' }).first().waitFor({ timeout: 30000 })
if (wavApply && status.speech.enabled) {
  await page.getByRole('button', { name: 'Start talking' }).click()
  await page.getByText('Transcribing…').first().waitFor({ timeout: 40000 })
  await thread(page).getByText(/apply the change/i).first().waitFor({ timeout: 40000 })
  log('spoken confirmation heard and shown, then applied')
} else {
  await page.getByRole('button', { name: 'Apply', exact: true }).click()
}
await page.getByRole('region', { name: 'Proposed change' }).first().locator('header strong', { hasText: 'Applied' }).waitFor({ timeout: 60000 })
await stage(page, 'Business Process')
await page.getByRole('region', { name: 'Process diagram' }).waitFor({ timeout: 30000 })
await shot(page, '04-process')
await stage(page, 'Data Model')
await page.getByRole('group', { name: 'Entity relationship diagram' }).waitFor()
await page.getByRole('button', { name: /^Shipment, \d+ attributes/ }).click()
await page.getByRole('switch').first().waitFor()
await shot(page, '05-data-model')
log('process diagram and entity-relationship view rendered from the saved specification')
await context.storageState().then(value => Object.assign(storage, value))

// ── 3. A change by chat: a role is reviewed, then applied ──
await page.getByLabel('Message to the assistant').fill('Add a warehouse manager role')
await page.getByRole('button', { name: 'Send message' }).click()
await page.getByRole('region', { name: 'Proposed change' }).last().waitFor({ timeout: 90000 })
await page.getByRole('button', { name: 'Apply', exact: true }).last().click()
await page.getByRole('region', { name: 'Proposed change' }).last().locator('header strong', { hasText: 'Applied' }).waitFor({ timeout: 60000 })
await stage(page, 'Roles')
await page.getByText(/Warehouse manager/i).first().waitFor()
log('role proposed in conversation, applied after review, shown in Roles & Permissions')

// ── 4. Answer the business decisions in Domain Knowledge ──
await stage(page, 'Domain Knowledge')
const inputs = page.getByPlaceholder('Record the decision')
await inputs.first().waitFor({ timeout: 15000 })
let remaining = await inputs.count()
log('open business decisions:', remaining)
while (remaining > 0) {
  await inputs.first().fill('Decided by the demo owner for this verification run.')
  await inputs.first().press('Enter')
  await page.waitForFunction(count => document.querySelectorAll('input[placeholder="Record the decision"]').length < count, remaining, { timeout: 30000 })
  remaining = await inputs.count()
}
await stage(page, 'Validation')
await page.getByRole('region', { name: 'Process approval' }).waitFor()
await shot(page, '06-validation')
const toFix = await page.locator('.sw-tiles [role=listitem]').first().innerText()
log('validation summary (to fix):', toFix.replace(/\n/g, ' '))
const aliceState = await context.storageState()

// ── 5. Bob (a separate approver) approves the process ──
const approver = await browser.newContext({ viewport: { width: 1440, height: 900 }, storageState: aliceState })
await signIn(approver, 'studio-bob')
bob = await approver.newPage(); watch(bob)
await bob.goto(projectUrl + '?stage=checks')
const processApproval = bob.getByRole('region', { name: 'Process approval' })
await processApproval.waitFor()
const ack = processApproval.getByRole('checkbox')
if (await ack.count()) await ack.check()
await processApproval.getByRole('button', { name: 'Approve process' }).click()
await bob.getByText(/Approved at revision/).first().waitFor({ timeout: 60000 })
log('process approved by a separate approver (Bob)')
await shot(bob, '07-process-approved')

// ── 6. Alice generates screens, Bob approves the design ──
await page.reload()
await stage(page, 'Screens')
await page.getByRole('button', { name: /Generate screens from the approved process/ }).click()
await page.getByText('Visual preview.').waitFor({ timeout: 60000 })
await shot(page, '08-screens')
log('screens generated from the approved process; labelled as a visual preview')
await bob.reload()
const designApproval = bob.getByRole('region', { name: 'Design approval' })
await designApproval.waitFor()
const designAck = designApproval.getByRole('checkbox')
if (await designAck.count()) await designAck.check()
await designApproval.getByRole('button', { name: 'Approve design' }).click()
await bob.getByText(/Approved at revision/).nth(1).waitFor({ timeout: 60000 })
log('design approved by Bob')

// ── 7. Generate the real application, run its tests, launch it, call it ──
await page.reload()
await stage(page, 'Generate Application')
await page.getByRole('heading', { name: 'Readiness' }).waitFor()
await page.getByRole('button', { name: 'Generate application', exact: true }).click()
await page.getByRole('region', { name: 'Generation result' }).waitFor({ timeout: 120000 })
const generated = await page.getByRole('region', { name: 'Generation result' }).innerText()
assert.match(generated, /Generated from revision/)
await shot(page, '09-generated')
log('generated:', generated.split('\n')[0])
await page.getByRole('button', { name: 'Run generated tests' }).click()
const tests = page.locator('.sw-tests')
await tests.waitFor({ timeout: 180000 })
assert.match(await tests.innerText(), /tests passed/)
log('generated tests:', (await tests.innerText()).split('\n')[0])
await page.getByRole('button', { name: 'Launch application' }).click()
const running = page.locator('.sw-running a').first()
await running.waitFor({ timeout: 60000 })
const url = await running.getAttribute('href')
assert.match(url, /^http:\/\/127\.0\.0\.1:\d+$/)
const demoUsers = await (await fetch(url + '/api/demo-users')).json()
assert.ok(Array.isArray(demoUsers) || typeof demoUsers === 'object')
await shot(page, '10-launched')
log('generated application is running at', url, 'and answers its own API')
await page.getByRole('button', { name: 'Stop', exact: true }).click()
await page.getByRole('button', { name: 'Launch application' }).waitFor()
log('stopped')

assert.deepEqual(errors, [])
console.log(JSON.stringify({ status: 'passed', pageErrors: errors.length }))
await browser.close()
