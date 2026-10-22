import { parse } from '@babel/parser'
let text = ''
for await (const part of process.stdin) text += part
const { source } = JSON.parse(text)
try {
  parse(source, { sourceType: 'module', plugins: ['typescript', 'jsx'] })
  process.stdout.write(JSON.stringify({ valid: true }))
} catch (error) {
  process.stdout.write(
    JSON.stringify({ valid: false, error: error.message, at_end: error.pos >= source.length - 8 }),
  )
}
