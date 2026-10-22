/** Build source as data. No generated build scripts, plugins or package installs execute. */
import { build, transform } from 'esbuild'
import { parse } from '@babel/parser'
import { readFile, mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const folder = path.dirname(fileURLToPath(import.meta.url))
const root = path.dirname(folder)
const sdk = await readFile(path.join(folder, 'studio-sdk.tsx'), 'utf8')
const entry = await readFile(path.join(folder, 'studio-entry.tsx'), 'utf8')
const forbidden = new Set([
  'window',
  'globalThis',
  'self',
  'parent',
  'top',
  'frames',
  'fetch',
  'XMLHttpRequest',
  'WebSocket',
  'EventSource',
  'Worker',
  'SharedWorker',
  'ServiceWorker',
  'navigator',
  'location',
  'localStorage',
  'sessionStorage',
  'indexedDB',
  'eval',
  'Function',
  'require',
  'process',
  'importScripts',
])
const packages = new Set([
  'react',
  'react-dom',
  'react-dom/client',
  'react/jsx-runtime',
  'lucide-react',
])
const input = JSON.parse(
  await new Promise((resolve, reject) => {
    let value = ''
    process.stdin.setEncoding('utf8')
    process.stdin.on('data', (part) => {
      value += part
      if (value.length > 600000) reject(new Error('Source exceeds build limit'))
    })
    process.stdin.on('end', () => resolve(value))
  }),
)
// A bounded source checkpoint supports local diagnostics/recovery after a failed build.
// Only one fixed JSON filename is written; generated paths are never used for this write.
const checkpointDir = await mkdtemp(path.join(tmpdir(), 'studio-model-source-'))
await writeFile(path.join(checkpointDir, 'source.json'), JSON.stringify(input))

let currentLines = []
let currentFile = ''
// Every violation in every file is collected, so one repair round can fix them all instead of one per attempt.
const violations = new Set()
// Report the exact line, so the model can repair the right statement instead of guessing.
function fail(node, message) {
  const line = node.loc?.start.line
  violations.add(
    `${currentFile}: ${message} [line ${line}: ${(currentLines[line - 1] ?? '').trim().slice(0, 120)}]`,
  )
}

function walk(node, parent = null) {
  if (!node || typeof node !== 'object') return
  if (
    node.type === 'Identifier' &&
    node.name === 'document' &&
    !(
      parent?.type === 'MemberExpression' &&
      parent.object === node &&
      !parent.computed &&
      ['activeElement', 'addEventListener', 'removeEventListener'].includes(parent.property?.name)
    )
  )
    fail(
      node,
      'Do not touch the page directly: document may only be used as document.activeElement, document.addEventListener or document.removeEventListener. To lock page scroll or style the page, change a CSS class on an element React renders, never document.body or document.documentElement',
    )
  if (node.type === 'Import') fail(node, 'Dynamic code loading is not supported')
  if (
    node.source?.value &&
    ['ImportDeclaration', 'ExportNamedDeclaration', 'ExportAllDeclaration'].includes(node.type)
  ) {
    const name = node.source.value
    if (name.startsWith('.')) {
      const resolved = path.posix
        .normalize(path.posix.join(path.posix.dirname(currentFile), name))
        .replace(/\.(tsx?|jsx?)$/, '')
      if (resolved === currentFile.replace(/\.(tsx?|jsx?)$/, ''))
        fail(
          node,
          'A module cannot import or re-export itself. Define the missing component here or import it from the module that actually implements it',
        )
    }
    if (name !== '@studio/sdk' && !packages.has(name) && !name.startsWith('.'))
      fail(node, `Import not allowed: ${name}`)
    if (name.endsWith('.css'))
      fail(node, 'Studio loads styles.css; do not import styles into JavaScript')
  }
  if (node.type === 'ImportExpression' || node.type === 'WithStatement')
    fail(node, 'Dynamic code loading is not supported')
  if (node.type === 'TSAsExpression' && node.typeAnnotation?.type === 'TSAnyKeyword')
    fail(
      node,
      'Use the declared SDK types instead of casting to any; records and instances come directly from useStudio()',
    )
  if (
    node.type === 'JSXAttribute' &&
    /^on(Change|Click|Submit)$/.test(node.name?.name ?? '') &&
    ['ArrowFunctionExpression', 'FunctionExpression'].includes(node.value?.expression?.type) &&
    node.value.expression.body?.type === 'BlockStatement' &&
    node.value.expression.body.body.length === 0
  )
    fail(
      node,
      'This interactive control has an empty handler. Connect it to form state or a real SDK action, or remove the control',
    )
  if (
    node.type === 'CallExpression' &&
    (node.callee?.name === 'advanceWorkflow' ||
      node.callee?.property?.name === 'advanceWorkflow') &&
    node.arguments[2]?.type === 'ObjectExpression'
  ) {
    for (const property of node.arguments[2].properties) {
      const key = property.key?.name ?? property.key?.value
      if (typeof key === 'string' && key.includes('.'))
        fail(
          property,
          'Workflow links contain entity IDs mapped to record IDs only. Save decision/field values through updateRecord with taskContext before advancing the workflow',
        )
    }
  }
  if (
    node.type === 'TSAsExpression' &&
    node.expression?.type === 'ObjectExpression' &&
    node.expression.properties.length === 0 &&
    ['Instance', 'any'].includes(node.typeAnnotation?.typeName?.name ?? node.typeAnnotation?.type)
  )
    fail(node, 'Use a real workflow instance from useStudio; an empty object cannot act as one')
  if (node.type === 'Identifier' && forbidden.has(node.name))
    fail(node, `Use @studio/sdk instead of ${node.name}`)
  if (
    (node.type === 'Identifier' || node.type === 'StringLiteral') &&
    ['dangerouslySetInnerHTML', '__proto__', 'prototype', 'constructor'].includes(
      node.name ?? node.value,
    )
  )
    fail(node, 'Unsafe DOM or prototype access is not supported')
  if (
    node.type === 'JSXOpeningElement' &&
    ['script', 'iframe', 'object', 'embed', 'link', 'style', 'base', 'meta'].includes(
      node.name?.name,
    )
  )
    fail(node, 'Executable or external markup is not supported')
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach((child) => walk(child, node))
    else if (value && typeof value === 'object') walk(value, node)
  }
}
try {
  const files = input.files
  if (!files['src/App.tsx'] || !files['src/styles.css'])
    throw new Error('Return src/App.tsx and src/styles.css')
  for (const [name, content] of Object.entries(files)) {
    if (
      !/^src\/[a-zA-Z0-9_/-]+\.(tsx|ts|css)$/.test(name) ||
      name.includes('..') ||
      name === 'src/main.tsx' ||
      name === 'src/studio-sdk.tsx'
    )
      throw new Error(`Unsupported source path: ${name}`)
    if (content.length > 200000) throw new Error('A source file exceeds the limit')
    if (name.endsWith('.css')) {
      content.split('\n').forEach((text, index) => {
        const hit = /@import|url\s*\(|expression\s*\(|<\/style/i.exec(text)
        if (hit)
          violations.add(
            `${name}: "${hit[0]}" is not allowed because styles must be self-contained (no @import, url() or expression()). Draw icons with inline SVG or lucide in React, use gradients for backgrounds and system fonts [line ${index + 1}: ${text.trim().slice(0, 120)}]`,
          )
      })
    } else {
      currentFile = name
      currentLines = content.split('\n')
      // esbuild reports a syntax error at its real line; Babel can pin the same error on an earlier line
      // (adjacent JSX siblings surfaced as a failure on the component's first line), which sends a repair to the wrong place.
      const syntax = await transform(content, {
        loader: name.endsWith('.ts') ? 'ts' : 'tsx',
        logLevel: 'silent',
      }).then(
        () => null,
        (error) => error.errors,
      )
      if (syntax) {
        for (const item of syntax.slice(0, 5))
          fail({ loc: { start: { line: item.location?.line } } }, item.text)
      } else {
        try {
          const parsed = parse(content, { sourceType: 'module', plugins: ['typescript', 'jsx'] })
          for (const comment of parsed.comments ?? []) {
            if (/@ts-(?:ignore|expect-error|nocheck)\b/.test(comment.value))
              fail(
                comment,
                'TypeScript errors must be fixed, not suppressed with compiler directives',
              )
            if (/(?:eslint|oxlint)-disable/.test(comment.value))
              fail(comment, 'React hook errors must be fixed, not suppressed with lint directives')
          }
          walk(parsed)
        } catch (error) {
          violations.add(`${name}: ${error.message}`)
        }
      }
    }
  }
  if (violations.size) throw new Error([...violations].join('\n'))
  const sources = { ...files, 'src/main.tsx': entry, 'src/studio-sdk.tsx': sdk }
  const stylesheet = await transform(files['src/styles.css'], { loader: 'css', logLevel: 'silent' })
  if (stylesheet.warnings.length)
    throw new Error(
      'src/styles.css: ' + stylesheet.warnings.map((warning) => warning.text).join('\n'),
    )
  const checkDir = await mkdtemp(path.join(tmpdir(), 'studio-source-check-'))
  for (const [name, text] of Object.entries(sources)) {
    const target = path.join(checkDir, name)
    await mkdir(path.dirname(target), { recursive: true })
    await writeFile(target, text)
  }
  await writeFile(
    path.join(checkDir, 'tsconfig.json'),
    JSON.stringify({
      compilerOptions: {
        target: 'ES2022',
        module: 'ESNext',
        moduleResolution: 'Bundler',
        jsx: 'react-jsx',
        strict: true,
        esModuleInterop: true,
        skipLibCheck: true,
        noEmit: true,
        paths: {
          '@studio/sdk': ['./src/studio-sdk.tsx'],
          react: [path.join(root, 'node_modules/@types/react/index.d.ts')],
          'react/*': [path.join(root, 'node_modules/@types/react/*')],
          'react-dom/*': [path.join(root, 'node_modules/@types/react-dom/*')],
          'lucide-react': [path.join(root, 'node_modules/lucide-react/dist/lucide-react.d.ts')],
        },
      },
      include: ['src'],
    }),
  )
  // The source can type-check and still throw when an event handler calls a
  // hook. Run the installed React rule against data files, without executing
  // generated source or loading generated lint configuration.
  const lintConfig = path.join(checkDir, 'studio-lint.json')
  await writeFile(
    lintConfig,
    JSON.stringify({ plugins: ['react'], rules: { 'react/rules-of-hooks': 'error' } }),
  )
  const hookCheck = spawnSync(
    process.execPath,
    [
      path.join(root, 'node_modules/oxlint/bin/oxlint'),
      '--config',
      lintConfig,
      '--disable-nested-config',
      '--no-ignore',
      '--react-plugin',
      '-A',
      'all',
      '-D',
      'react/rules-of-hooks',
      '--format',
      'unix',
      '--threads',
      '1',
      path.join(checkDir, 'src'),
    ],
    { encoding: 'utf8', timeout: 15000, windowsHide: true },
  )
  if (hookCheck.status !== 0) {
    const diagnostics = (hookCheck.stdout || hookCheck.stderr || 'React hook checker unavailable')
      .split('\n')
      .map((line) => {
        const match = line.match(/(?:^|[/\\])(src[/\\][^:]+):(\d+):(\d+):\s*(.*)/)
        return match
          ? `${match[1].replaceAll('\\', '/')}: ${match[4]} [line ${match[2]}: React hook placement]`
          : line
      })
      .join('\n')
    throw new Error(diagnostics)
  }
  const checked = spawnSync(
    process.execPath,
    [
      path.join(root, 'node_modules/typescript/bin/tsc'),
      '--project',
      path.join(checkDir, 'tsconfig.json'),
      '--pretty',
      'false',
    ],
    { encoding: 'utf8', timeout: 45000, windowsHide: true },
  )
  // A bundle can compile while a form sends the wrong ID or an action has no record revision.
  // Require the same strict type contract that the editable export ships with.
  const report = (checked.stdout || checked.stderr || 'Compiler unavailable').replaceAll(
    checkDir,
    '',
  )
  const lines = report.split('\n').filter((line) => /error TS\d+/.test(line))
  if (checked.status !== 0)
    throw new Error(
      `TypeScript check failed:\n${(lines.length ? lines.join('\n') : report).slice(0, 30000)}`,
    )
  const result = await build({
    entryPoints: ['src/main.tsx'],
    absWorkingDir: root,
    bundle: true,
    write: false,
    minify: true,
    format: 'iife',
    platform: 'browser',
    target: 'es2022',
    jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"' },
    logLevel: 'silent',
    plugins: [
      {
        name: 'studio-virtual-source',
        setup(builder) {
          builder.onResolve({ filter: /.*/ }, (args) => {
            if (args.kind === 'entry-point') return { path: 'src/main.tsx', namespace: 'studio' }
            if (args.path === '@studio/sdk')
              return { path: 'src/studio-sdk.tsx', namespace: 'studio' }
            if (args.namespace !== 'studio') return undefined
            if (packages.has(args.path)) return undefined
            if (!args.path.startsWith('.')) throw new Error(`Import not allowed: ${args.path}`)
            const base = path.posix.normalize(
              path.posix.join(path.posix.dirname(args.importer || 'src/main.tsx'), args.path),
            )
            const found = [base, `${base}.tsx`, `${base}.ts`, `${base}/index.tsx`].find((name) =>
              Object.hasOwn(sources, name),
            )
            if (!found) throw new Error(`Local import does not exist: ${args.path}`)
            return { path: found, namespace: 'studio' }
          })
          builder.onLoad({ filter: /.*/, namespace: 'studio' }, (args) => ({
            contents: sources[args.path],
            loader: args.path.endsWith('.tsx') ? 'tsx' : args.path.endsWith('.css') ? 'css' : 'ts',
            resolveDir: root,
          }))
        },
      },
    ],
  })
  // CSS is provided separately; generated source should never import it into JS.
  const js = result.outputFiles.find((file) => !file.path.endsWith('.css'))?.text
  if (!js) throw new Error('No executable bundle was emitted')
  process.stdout.write(
    JSON.stringify({
      js,
      css: files['src/styles.css'],
      sdk_source: sdk,
      entry_source: entry,
      checks: [
        'Source syntax parses',
        'React hook placement check passes',
        'TypeScript strict check passes',
        'Imports resolve through the allowlist',
        'React browser bundle builds',
        'Self-contained stylesheet checked',
      ],
    }),
  )
} catch (error) {
  process.stdout.write(
    JSON.stringify({
      error: (error.errors?.map((item) => item.text).join('\n') ?? error.message).slice(0, 30000),
    }),
  )
  process.exitCode = 1
}
