import { useEffect, useRef, useState } from 'react'
import type { AppTemplate } from '../../../api/appTemplates'
import { TemplateApp } from '../../../templates/TemplateApp'

const WIDTH = 1280
const HEIGHT = 800

/** A live, scaled-down render of the template's first page: the same engine as the full preview, not a screenshot. */
export function TemplateThumb({ template }: { template: AppTemplate }) {
  const frame = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.25)
  useEffect(() => {
    const element = frame.current
    if (!element) return
    const measure = () => setScale(element.clientWidth / WIDTH || 0.25)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return (
    <div ref={frame} className="tg-thumb" aria-hidden="true">
      <div
        className="tg-thumb__canvas"
        style={{ width: WIDTH, height: HEIGHT, transform: `scale(${scale})` }}
      >
        <TemplateApp template={template} still />
      </div>
    </div>
  )
}
