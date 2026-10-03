import { company } from '../data/content'
import { usePageMeta } from '../hooks/usePageMeta'
import './pages.css'

const copy = {
  legal: {
    title: 'Legal',
    path: '/legal',
    paragraphs: [
      `${company.name} is a fictional company created for demonstration purposes. It does not exist, and nothing on this website is an offer to sell or supply.`,
      'Machine names, plants, brands and parts information come from a demonstration catalogue. They are not real products or real data.',
    ],
  },
  privacy: {
    title: 'Privacy',
    path: '/privacy',
    paragraphs: [
      'This demonstration website does not collect personal data, set tracking cookies or process forms.',
      `Contact links open your email client. ${company.disclaimer}`,
    ],
  },
} as const

export default function LegalPage({ kind }: { kind: keyof typeof copy }) {
  const page = copy[kind]
  usePageMeta({ title: page.title, description: `${page.title} information for the Noordveld Machinery B.V. demonstration website.`, path: page.path })
  return (
    <section className="page-head" aria-labelledby="legal-title">
      <div className="container simple simple--text">
        <h1 id="legal-title" className="h1">
          {page.title}
        </h1>
        {page.paragraphs.map((p) => (
          <p key={p} className="lead">
            {p}
          </p>
        ))}
        <p className="note">{company.disclaimer}</p>
      </div>
    </section>
  )
}
