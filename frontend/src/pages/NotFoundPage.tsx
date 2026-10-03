import { ButtonLink } from '../components/ButtonLink'
import { usePageMeta } from '../hooks/usePageMeta'
import './pages.css'

export default function NotFoundPage() {
  usePageMeta({ title: 'Page not found', description: 'This page does not exist.', path: '/404' })
  return (
    <section className="page-head page-head--centered" aria-labelledby="nf-title">
      <div className="container simple">
        <h1 id="nf-title" className="hero-title">
          Not found.
        </h1>
        <p className="lead">That page doesn’t exist. Try the machine range instead.</p>
        <ButtonLink to="/machines">Explore Machines</ButtonLink>
      </div>
    </section>
  )
}
