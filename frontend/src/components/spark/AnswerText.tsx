import type { ReactNode } from 'react'
import { SPARK_CHAT_ROUTE } from '../../data/content'

/** The chat link for a part: the conversation opens it in place (see SparkHome), so the answer stays a sentence. */
export const partHref = (partNumber: string) =>
  `${SPARK_CHAT_ROUTE}?part=${encodeURIComponent(partNumber)}`

/** Known part numbers in plain text become links. Only numbers this reply's records carry are linked; nothing is guessed. */
function linked(text: string, parts: readonly string[], key: string): ReactNode[] {
  const known = [...new Set(parts)].filter(Boolean).sort((a, b) => b.length - a.length)
  if (!known.length) return [text]
  const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.split(new RegExp(`(${known.map(escape).join('|')})`, 'g')).map((piece, n) =>
    known.includes(piece) ? (
      <a key={`${key}-${n}`} href={partHref(piece)}>
        {piece}
      </a>
    ) : (
      piece
    ),
  )
}

function inline(text: string, parts: readonly string[] = []): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g)
    .map((part, index) => {
      if (part.startsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>
      if (part.startsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>
      const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/)
      if (link)
        return (
          <a key={index} href={link[2]} target="_blank" rel="noopener noreferrer">
            {link[1]}
          </a>
        )
      return linked(part, parts, String(index))
    })
}

/** A small safe renderer for the text formats Spark can return. HTML stays plain text. */
export function AnswerText({ text, parts = [] }: { text: string; parts?: readonly string[] }) {
  return (
    <div className="spark-answer-text">
      {text
        .split(/(```[\s\S]*?```)/g)
        .filter(Boolean)
        .map((chunk, i) => {
          if (chunk.startsWith('```')) {
            const code = chunk.slice(3, -3).replace(/^[\w+-]*\n/, '')
            return (
              <pre key={i}>
                <code>{code}</code>
              </pre>
            )
          }
          return chunk
            .trim()
            .split(/\n\s*\n/)
            .map((block, j) => {
              const lines = block.split('\n')
              const cells = (line: string) =>
                line
                  .trim()
                  .replace(/^\||\|$/g, '')
                  .split('|')
                  .map((cell) => cell.trim())
              if (
                lines.length > 2 &&
                lines[0].includes('|') &&
                cells(lines[1]).every((cell) => /^:?-{3,}:?$/.test(cell))
              ) {
                const headers = cells(lines[0])
                return (
                  <div className="spark-answer-table" key={`${i}-${j}`}>
                    <table aria-label="Answer table">
                      <thead>
                        <tr>
                          {headers.map((cell, k) => (
                            <th scope="col" key={k}>
                              {inline(cell)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {lines.slice(2).map((line, row) => (
                          <tr key={row}>
                            {headers.map((_, column) => (
                              <td key={column}>{inline(cells(line)[column] ?? '')}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              }
              if (lines.every((line) => /^[-*] /.test(line)))
                return (
                  <ul key={`${i}-${j}`}>
                    {lines.map((line, k) => (
                      <li key={k}>{inline(line.slice(2), parts)}</li>
                    ))}
                  </ul>
                )
              if (lines.every((line) => /^\d+\. /.test(line)))
                return (
                  <ol key={`${i}-${j}`}>
                    {lines.map((line, k) => (
                      <li key={k}>{inline(line.replace(/^\d+\. /, ''), parts)}</li>
                    ))}
                  </ol>
                )
              if (/^#{1,3} /.test(block))
                return <h3 key={`${i}-${j}`}>{inline(block.replace(/^#{1,3} /, ''))}</h3>
              return <p key={`${i}-${j}`}>{inline(block, parts)}</p>
            })
        })}
    </div>
  )
}
