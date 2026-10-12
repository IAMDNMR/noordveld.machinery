import { CommerceWorkspace } from '../components/commerce/CommerceWorkspace'
import { usePageMeta } from '../hooks/usePageMeta'
import { CartProvider } from '../store/CartContext'
import '../styles/wf.css'

export const COMMERCE_ROUTE = '/commerce'

/**
 * Agentic E-Commerce workspace: one commerce assistant over part discovery, shipment logistics and warranty traceability. The page owns no business rule: it sends the
 * user's words (and the references the last answer returned) to the Commerce Agent API and shows the contexts and evidence the backend sends back.
 */
export default function CommercePage() {
  usePageMeta({ title: 'Agentic E-Commerce', description: 'Ask about a part, a shipment or a warranty. Every answer comes from Noordveld records and shows its evidence.', path: COMMERCE_ROUTE })
  return (
    <main className="cw-page">
      <header className="cw-hero">
        <h1>Agentic E-Commerce</h1>
        <p>Find the right part, follow its shipment and check its warranty in one conversation. The assistant explains; the Noordveld records decide.</p>
      </header>
      <CartProvider>
        <CommerceWorkspace />
      </CartProvider>
    </main>
  )
}
