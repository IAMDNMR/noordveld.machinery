/** Render a generated application in a real browser and report measurable UI defects as data.
 * Input (stdin): {"html": "<complete application document>"}. Output (stdout): {"findings": [...], "metrics": {...}}.
 * It only reports what is wrong; it never dictates what an application should contain or how it must look. */
import { chromium } from 'playwright-core'
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'

const axeSource = readFileSync(
  createRequire(import.meta.url).resolve('axe-core/axe.min.js'),
  'utf8',
)
const WIDTHS = [375, 768, 1280]

const input = JSON.parse(
  await new Promise((resolve) => {
    let value = ''
    process.stdin.setEncoding('utf8')
    process.stdin.on('data', (part) => (value += part))
    process.stdin.on('end', () => resolve(value))
  }),
)
// The preview CSP blocks the injected checker script; the gate renders the same document without it.
const html = input.html.replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/, '')

const findings = []
const add = (id, severity, message, evidence = {}) =>
  findings.push({ id, severity, message, evidence })

/** Runs inside the page: everything the checks need, measured from the live DOM. */
function measure() {
  const defined = new Set()
  let mediaRules = 0
  const collect = (rules) => {
    for (const rule of rules) {
      if (rule.media) mediaRules++
      if (rule.selectorText)
        for (const m of rule.selectorText.matchAll(/\.([\w-]+)/g)) defined.add(m[1])
      if (rule.cssRules) collect(rule.cssRules)
    }
  }
  for (const sheet of document.styleSheets) collect(sheet.cssRules)
  const used = new Set()
  for (const el of document.querySelectorAll('[class]'))
    for (const name of el.classList) used.add(name)
  const visible = (el) => {
    const r = el.getBoundingClientRect()
    const s = getComputedStyle(el)
    return (
      r.width > 0 &&
      r.height > 0 &&
      s.visibility !== 'hidden' &&
      s.display !== 'none' &&
      r.right > 0 &&
      r.left < innerWidth &&
      r.bottom > 0 &&
      r.top < innerHeight
    )
  }
  const navs = [...document.querySelectorAll('nav, [role="navigation"]')]
  const navItems = navs.flatMap((n) => [...n.querySelectorAll('a, button, [role="tab"]')])
  const navTriggers = [
    ...document.querySelectorAll('button[aria-controls], button[aria-label]'),
  ].filter((el) =>
    /navigation|menu/i.test(
      `${el.getAttribute('aria-controls') ?? ''} ${el.getAttribute('aria-label') ?? ''}`,
    ),
  )
  const small = [...document.querySelectorAll('button, a[href], input, select, textarea')]
    .filter((el) => visible(el))
    .filter((el) => {
      const r = el.getBoundingClientRect()
      return r.width < 24 || r.height < 24
    })
  return {
    // lucide-* classes are added by the icon library itself, not written by the model.
    unstyled: [...used].filter((c) => !defined.has(c) && !c.startsWith('lucide')),
    mediaRules,
    overflow: document.documentElement.scrollWidth - innerWidth,
    overflowElements: [...document.querySelectorAll('body *')]
      .filter((el) => el.getBoundingClientRect().right > innerWidth + 1)
      .slice(0, 6)
      .map((el) => ({
        tag: el.tagName.toLowerCase(),
        className: String(el.className).slice(0, 90),
      })),
    textLength: (document.body.innerText || '').trim().length,
    navCount: navs.length,
    navVisible: navItems.filter(visible).length,
    navTriggersVisible: navTriggers.filter(visible).length,
    navItems: navItems.length,
    smallTargets: small.length,
  }
}

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const metrics = {}
try {
  for (const width of WIDTHS) {
    const page = await browser.newPage({ viewport: { width, height: 900 } })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
    await page.setContent(html, { waitUntil: 'load' })
    await page.waitForTimeout(400)
    const m = await page.evaluate(measure)
    metrics[width] = m
    if (errors.length)
      add('runtime-error', 'error', `The page logged ${errors.length} error(s) at ${width}px.`, {
        errors: errors.slice(0, 3),
      })
    if (m.textLength < 20)
      add('blank-render', 'error', `Nothing meaningful rendered at ${width}px.`)
    if (m.overflow > 1)
      add(
        'horizontal-overflow',
        'error',
        `Content is ${m.overflow}px wider than the screen at ${width}px.`,
        { width, elements: m.overflowElements },
      )
    if (m.navItems && !m.navVisible && !m.navTriggersVisible)
      add(
        'navigation-hidden',
        'error',
        `Navigation exists but neither its items nor an opening control is visible at ${width}px.`,
        { width },
      )
    if (width === 375 && m.smallTargets)
      add(
        'small-touch-targets',
        'warning',
        `${m.smallTargets} interactive element(s) are smaller than 24x24px on a phone.`,
      )
    if (width === 1280) {
      if (m.unstyled.length)
        add(
          'unstyled-classes',
          'error',
          `${m.unstyled.length} class name(s) are used in the markup but have no CSS rule.`,
          { classes: m.unstyled.slice(0, 30) },
        )
      if (!m.mediaRules)
        add(
          'no-responsive-rules',
          'error',
          'The stylesheet has no @media rules, so the layout cannot adapt to other screen sizes.',
        )
      await page.evaluate(axeSource)
      const axe = await page.evaluate(() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa'] }))
      for (const v of axe.violations.filter((x) => ['serious', 'critical'].includes(x.impact)))
        add('accessibility-' + v.id, 'error', `${v.help} (${v.nodes.length} element(s)).`, {
          example: v.nodes[0]?.target?.join(' '),
        })
      // Preview user IDs intentionally differ from roles. Exercise a visible
      // global identity select so a role-as-user bug is not masked by fixtures.
      const roleNames = await page.evaluate(() => {
        const bootstrap = document.getElementById('studio-bootstrap')
        return Object.values(JSON.parse(bootstrap?.textContent ?? '{}').app?.roles ?? {})
      })
      const selects = page.locator('select')
      for (let index = 0; index < (await selects.count()); index++) {
        const select = selects.nth(index)
        if (
          !(await select.isVisible()) ||
          (await select.evaluate((el) => !!el.closest('main, [role="main"]')))
        )
          continue
        const options = await select
          .locator('option')
          .evaluateAll((nodes) =>
            nodes.map((node) => ({ value: node.value, label: node.textContent.trim() })),
          )
        if (options.filter((option) => roleNames.includes(option.label)).length < 2) continue
        const previous = await select.inputValue()
        const target = options.find(
          (option) => option.value && option.value !== previous && roleNames.includes(option.label),
        )
        if (!target) continue
        const beforeErrors = errors.length
        await select.selectOption(target.value)
        await page.waitForTimeout(150)
        const alerts = await page.locator('[role="alert"]').allInnerTexts()
        if (errors.length > beforeErrors || alerts.length)
          add(
            'identity-switch-failed',
            'error',
            'Switching the application identity raised an error. Use users[].id with signIn, never a role ID.',
            { messages: [...errors.slice(beforeErrors), ...alerts].slice(0, 3) },
          )
        await page.setContent(html, { waitUntil: 'load' })
        await page.waitForTimeout(100)
        break
      }
      // Last, because it changes the page: if the app offers demo data, loading it must work and be labelled.
      const demo = page.getByRole('button', { name: /demo data|sample data/i }).first()
      if (await demo.count()) {
        const before = await page.evaluate(() => document.body.innerText.length)
        const errorsBefore = errors.length
        await demo.click()
        await page.waitForTimeout(2500)
        const alerts = await page.locator('[role="alert"]').allInnerTexts()
        const after = await page.evaluate(() => document.body.innerText)
        if (
          errors.length > errorsBefore ||
          alerts.length ||
          /failed to load demo data/i.test(after)
        )
          add('demo-data-failed', 'error', 'Loading the demo data raised an error.', {
            messages: [...errors.slice(errorsBefore), ...alerts].slice(0, 3),
          })
        else if (after.length <= before)
          add('demo-data-empty', 'error', 'Loading the demo data changed nothing on screen.', {
            before,
            after: after.length,
            visibleEnd: after.slice(-300),
          })
        else if (!/demo/i.test(after))
          add(
            'demo-data-unlabelled',
            'error',
            'Demo records are shown without any visible "Demo" label.',
          )
      }
      // Every role must have a usable landing state, including a role with no current tasks.
      // Select each trusted preview identity; this does not assume a generated layout.
      const bootstrap =
        /(<script id="studio-bootstrap" type="application\/json">)([\s\S]*?)(<\/script>)/.exec(html)
      if (bootstrap) {
        const data = JSON.parse(bootstrap[2])
        for (const [role, label] of Object.entries(data.app?.roles ?? {})) {
          const variant = html.replace(
            bootstrap[0],
            bootstrap[1] + JSON.stringify({ ...data, preview_role: role }) + bootstrap[3],
          )
          await page.setContent(variant, { waitUntil: 'load' })
          await page.waitForTimeout(100)
          const state = await page.evaluate(() => {
            const main =
              document.querySelector('#app main, #app [role="main"]') ??
              document.querySelector('#app')
            return {
              text: (main?.innerText ?? '').trim(),
              actions:
                main?.querySelectorAll('button:not([disabled]), a[href], input:not([disabled])')
                  .length ?? 0,
            }
          })
          if (state.text.length < 100 && !state.actions)
            add('role-empty', 'error', `The landing workspace is empty for ${label} (${role}).`, {
              role,
            })
          const sample = page.getByRole('button', { name: /load (demo|sample) data/i }).first()
          if (await sample.count()) {
            await sample.click()
            await page.waitForTimeout(150)
          }
          const navigation = 'nav button, nav a[href^="#"]'
          const count = await page.locator(navigation).count()
          const destinations = new Map()
          for (let index = 0; index < count; index++) {
            const item = page.locator(navigation).nth(index)
            if (!(await item.isVisible())) continue
            const name = (await item.innerText()).trim()
            if (!name) continue
            const beforeErrors = errors.length
            await item.click()
            await page.waitForTimeout(100)
            // Global navigation must change the application, not just the
            // selected item's styling. Local filters can legitimately show the
            // same empty list, so this check excludes navigation inside main.
            const globalNavigation = await item.evaluate(
              (element) => !element.closest('main, [role="main"]'),
            )
            if (globalNavigation) {
              const destination = await page.evaluate(() => {
                const main = document.querySelector('#app main, #app [role="main"]')
                return [
                  main?.innerText ?? '',
                  ...[...document.querySelectorAll('[role="dialog"], dialog[open]')].map(
                    (node) => node.innerText,
                  ),
                ]
                  .join('\n')
                  .trim()
              })
              const previous = destinations.get(destination)
              if (destination && previous && previous !== name)
                add(
                  'navigation-no-change',
                  'error',
                  `${name} and ${previous} show the same application content for ${label}; navigation may only change its highlight.`,
                  { role, pages: [previous, name] },
                )
              else if (destination) destinations.set(destination, name)
            }
            for (const screenWidth of WIDTHS) {
              await page.setViewportSize({ width: screenWidth, height: 900 })
              const surface = await page.evaluate(measure)
              if (surface.overflow > 2)
                add(
                  'navigation-overflow',
                  'error',
                  `${name} overflows at ${screenWidth}px for ${label}.`,
                  { role, page: name, elements: surface.overflowElements },
                )
              if (surface.unstyled.length)
                add('navigation-unstyled', 'error', `${name} uses classes without styles.`, {
                  role,
                  page: name,
                  classes: surface.unstyled,
                })
            }
            await page.setViewportSize({ width: 1280, height: 900 })
            await page.evaluate(axeSource)
            const accessibility = await page.evaluate(() =>
              axe.run(document, { runOnly: ['wcag2a', 'wcag2aa'] }),
            )
            for (const violation of accessibility.violations.filter((value) =>
              ['serious', 'critical'].includes(value.impact),
            ))
              add('navigation-accessibility', 'error', `${name}: ${violation.help}`, {
                role,
                page: name,
                example: violation.nodes[0]?.target?.join(' '),
              })
            const create = page
              .locator('main')
              .getByRole('button', { name: /^(new |add |create |place order)/i })
              .first()
            if (await create.count()) {
              await create.click()
              const dialog = page.getByRole('dialog').first()
              if (await dialog.count()) {
                const input = dialog
                  .locator('input:not([disabled]):not([type]), input[type="text"]:not([disabled])')
                  .first()
                if (await input.count()) {
                  await input.fill('Preview input check')
                  await page.waitForTimeout(50)
                  if (!(await input.evaluate((element) => element === document.activeElement)))
                    add(
                      'dialog-focus',
                      'error',
                      `${name}: editing a form moves keyboard focus away from its input.`,
                      { role, page: name },
                    )
                }
                await page.keyboard.press('Escape')
              }
            }
            if (errors.length > beforeErrors)
              add(
                'navigation-runtime-error',
                'error',
                `${name} raised a browser error for ${label}.`,
                { role, page: name, errors: errors.slice(beforeErrors, beforeErrors + 3) },
              )
          }
        }
      }
    }
    await page.close()
  }
} finally {
  await browser.close()
}
process.stdout.write(JSON.stringify({ findings, metrics }))
