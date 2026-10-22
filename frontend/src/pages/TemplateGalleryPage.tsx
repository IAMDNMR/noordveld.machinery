import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { ensureOrganization } from '../api/studio'
import { usePageMeta } from '../hooks/usePageMeta'
import { TemplateGallery } from '../components/studio/templates/TemplateGallery'
import '../components/studio/templates/templates.css'

/** The application template library, browsable outside a project. Choosing one happens inside a project's Screens stage. */
export default function TemplateGalleryPage() {
  usePageMeta({
    title: 'Application templates | Design Studio',
    description: 'Domain application templates for Design Studio.',
    path: '/design-studio/templates',
  })
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    ensureOrganization()
      .then(() => setReady(true))
      .catch(() => setError('Sign in to Design Studio to browse the template library.'))
  }, [])
  return (
    <main className="tgp">
      <Link to="/design-studio" className="tgp-back">
        <ArrowLeft size={16} aria-hidden="true" /> Design Studio
      </Link>
      <header className="tgp-head">
        <p className="tg-eyebrow">Template library</p>
        <h1>Application templates</h1>
        <p className="tg-muted">
          Each template is a complete application design for one domain, with its own look,
          navigation and pages. Open one to try it at desktop, tablet and phone size. Inside a
          project, Design Studio recommends the templates that fit your requirements.
        </p>
      </header>
      {error ? (
        <p className="tg-state" role="alert">
          {error}
        </p>
      ) : ready ? (
        <TemplateGallery />
      ) : (
        <p className="tg-muted">Opening the library…</p>
      )}
    </main>
  )
}
