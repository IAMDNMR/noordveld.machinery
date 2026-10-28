import { Link } from 'react-router-dom'
import { CineHero, ProcessFlow } from '../components/cine/Cine'
import { company } from '../data/content'
import { usePageMeta } from '../hooks/usePageMeta'
import './pages.css'
import './pages-dark.css'
import './legal.css'

type Block = { heading: string; body: string[] }

const copy = {
  legal: {
    title: ['Legal', 'notice.'],
    path: '/legal',
    eyebrow: 'Legal',
    lead: `${company.name} is a fictional company created for demonstration purposes.`,
    flowTitle: 'Where every fact on this site comes from',
    flow: [
      {
        title: 'Demonstration catalogue',
        text: 'Machines, parts, plants, dealers and depots are demonstration records.',
      },
      {
        title: 'Connected graph',
        text: 'They are stored as one connected graph, read only by this site.',
      },
      { title: 'Fixed queries', text: 'Pages and Spark read it through fixed, reviewed queries.' },
      {
        title: 'Labelled answers',
        text: 'Synthetic values are labelled as demo wherever they appear.',
      },
    ],
    blocks: [
      {
        heading: 'The company',
        body: [
          `${company.name} does not exist. Nothing on this website is an offer to sell or supply, and no contract can be formed through it.`,
        ],
      },
      {
        heading: 'Catalogue and prices',
        body: [
          'Machine names, plants, brands and parts information come from a demonstration catalogue. They are not real products or real data.',
          'Prices, stock levels, transport rates and delivery estimates are synthetic demonstration values. No payment is ever taken.',
        ],
      },
      {
        heading: 'Spark',
        body: [
          'Spark uses a language model only to understand questions. Every fact in an answer is read from the demonstration graph; the model never writes prices, stock, fitment or rankings.',
          'An order is only created after you confirm it, and only the backend can confirm that it was created.',
        ],
      },
    ] as Block[],
  },
  privacy: {
    title: ['Privacy,', 'by consent.'],
    path: '/privacy',
    eyebrow: 'Privacy',
    lead: 'This demonstration keeps as little about you as it can, and nothing optional without your agreement.',
    flowTitle: 'What happens to your saved profile',
    flow: [
      {
        title: 'You agree',
        text: 'Nothing is saved until you tick the consent box on your profile.',
      },
      {
        title: 'Stored for you',
        text: 'Machine, delivery and contact details, kept for your sign-in only.',
        to: '/profile',
      },
      {
        title: 'Pre-filled',
        text: 'Spark and checkout fill in what you saved, instead of asking again.',
      },
      { title: 'You confirm', text: 'Every order shows each detail for your confirmation first.' },
      {
        title: 'Erase any time',
        text: 'Untick consent or press Erase, and the profile is deleted.',
        to: '/profile',
      },
    ],
    blocks: [
      {
        heading: 'What is stored',
        body: [
          'Signing in keeps a signed session cookie so the site knows which demonstration account you use. It is not used for tracking.',
          'Orders you place keep the requester, receiver and delivery details you entered, because the order needs them.',
          'A profile is stored only with your consent, and only the fields you fill in.',
        ],
      },
      {
        heading: 'What is not',
        body: [
          'No tracking or advertising cookies are set, and nothing is shared with third parties.',
          'Spark conversation history stays in this browser tab. The server keeps no conversation history; recent answers are cached in memory for a few minutes so a follow-up can reuse them.',
        ],
      },
      {
        heading: 'Contact',
        body: [`Contact links open your email client. ${company.disclaimer}`],
      },
    ] as Block[],
  },
} as const

export default function LegalPage({ kind }: { kind: keyof typeof copy }) {
  const page = copy[kind]
  usePageMeta({
    title: page.eyebrow,
    description: `${page.eyebrow} information for the Noordveld Machinery B.V. demonstration website.`,
    path: page.path,
  })
  return (
    <div className="legal">
      <CineHero
        id="legal-title"
        eyebrow={page.eyebrow}
        lines={[...page.title]}
        lead={<p>{page.lead}</p>}
      >
        <nav className="legal__switch" aria-label="Legal pages">
          <Link to="/legal" aria-current={kind === 'legal' ? 'page' : undefined}>
            Legal notice
          </Link>
          <Link to="/privacy" aria-current={kind === 'privacy' ? 'page' : undefined}>
            Privacy
          </Link>
        </nav>
      </CineHero>
      <section className="legal__flow" aria-labelledby="legal-flow-title">
        <div className="container">
          <h2 id="legal-flow-title">{page.flowTitle}</h2>
          <ProcessFlow label={page.flowTitle} steps={[...page.flow]} />
        </div>
      </section>
      <div className="container legal__body">
        {page.blocks.map((block, index) => (
          <section key={block.heading} aria-labelledby={`legal-${index}`}>
            <span className="legal__index" aria-hidden="true">
              {String(index + 1).padStart(2, '0')}
            </span>
            <h2 id={`legal-${index}`}>{block.heading}</h2>
            {block.body.map((text) => (
              <p key={text}>{text}</p>
            ))}
          </section>
        ))}
        <p className="legal__note">{company.disclaimer}</p>
      </div>
    </div>
  )
}
