/** Renders a stage name so hyphenated words such as "E-Commerce" never break across lines. */
export function NoBreakName({ name }: { name: string }) {
  return name.split(' ').map((word, i) => (
    <span key={word} className={word.includes('-') ? 'nowrap' : undefined}>
      {i > 0 ? ' ' : ''}
      {word}
    </span>
  ))
}
