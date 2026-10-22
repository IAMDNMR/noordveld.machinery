/** Extract TypeScript declarations as data; never import or execute generated modules. */
import { parse } from '@babel/parser'

const input = JSON.parse(
  await new Promise((resolve) => {
    let value = ''
    process.stdin.setEncoding('utf8')
    process.stdin.on('data', (part) => {
      value += part
    })
    process.stdin.on('end', () => resolve(value))
  }),
)
const contracts = {}
for (const [name, text] of Object.entries(input.files)) {
  if (!/\.tsx?$/.test(name)) continue
  let body
  try {
    body = parse(text, {
      sourceType: 'module',
      plugins: ['typescript', 'jsx'],
      errorRecovery: true,
    }).program.body
  } catch {
    contracts[name] = 'This module does not parse yet. Repair it before relying on new exports.'
    continue
  }
  const source = (node) => text.slice(node.start, node.end)
  const aliases = new Set(
    body.flatMap((node) =>
      node.type === 'ExportDefaultDeclaration' && node.declaration?.type === 'Identifier'
        ? [node.declaration.name]
        : node.type === 'ExportNamedDeclaration'
          ? (node.specifiers ?? []).map((item) => item.local?.name)
          : [],
    ),
  )
  const declarations = []
  for (const node of body) {
    const declaration = node.declaration ?? node
    const exported = node.type.startsWith('Export') || aliases.has(declaration.id?.name)
    if (
      [
        'ImportDeclaration',
        'TSInterfaceDeclaration',
        'TSTypeAliasDeclaration',
        'ExportAllDeclaration',
      ].includes(declaration.type) ||
      (node.type === 'ExportNamedDeclaration' && !node.declaration) ||
      (node.type === 'ExportDefaultDeclaration' && declaration.type === 'Identifier')
    ) {
      declarations.push(source(node))
    } else if (exported && declaration.type === 'FunctionDeclaration') {
      declarations.push(
        declaration.body ? text.slice(node.start, declaration.body.start) + ';' : source(node),
      )
    } else if (exported && declaration.type === 'VariableDeclaration') {
      for (const variable of declaration.declarations) {
        const initializer = variable.init
        const signature =
          initializer &&
          ['ArrowFunctionExpression', 'FunctionExpression'].includes(initializer.type)
            ? '(' +
              initializer.params.map(source).join(', ') +
              ')' +
              (initializer.returnType ? source(initializer.returnType) : '')
            : variable.id.typeAnnotation
              ? source(variable.id.typeAnnotation).replace(/^:/, '')
              : '(value; inspect its declared usage)'
        declarations.push(
          'export const ' + (variable.id.name ?? source(variable.id)) + ': ' + signature + ';',
        )
      }
    }
  }
  contracts[name] = declarations.join('\n')
}
process.stdout.write(JSON.stringify(contracts))
