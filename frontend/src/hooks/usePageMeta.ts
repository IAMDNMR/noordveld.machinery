import { useEffect } from 'react'

interface PageMeta {
  title: string
  description: string
  /** Path such as "/machines/nv-2100", used for og:url and the canonical link */
  path: string
}

const SITE = 'Noordveld Machinery B.V.'

function setMeta(selector: string, attr: 'name' | 'property', key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(selector)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

/** Sets title, description, Open Graph and canonical link for the current page. */
export function usePageMeta({ title, description, path }: PageMeta): void {
  useEffect(() => {
    const full = title.includes(SITE) ? title : `${title} | ${SITE}`
    document.title = full
    setMeta('meta[name="description"]', 'name', 'description', description)
    setMeta('meta[property="og:title"]', 'property', 'og:title', full)
    setMeta('meta[property="og:description"]', 'property', 'og:description', description)
    setMeta('meta[property="og:url"]', 'property', 'og:url', `${window.location.origin}${path}`)
    let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
    if (!link) {
      link = document.createElement('link')
      link.rel = 'canonical'
      document.head.appendChild(link)
    }
    link.href = `${window.location.origin}${path}`
  }, [title, description, path])
}
