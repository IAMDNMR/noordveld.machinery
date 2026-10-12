import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { SiteLayout } from './components/SiteLayout'
import { HomePage } from './pages/HomePage'
import { SessionProvider, useSession } from './store/session'

// Secondary routes load on demand to keep the first bundle small
const MachinesPage = lazy(() => import('./pages/MachinesPage'))
const MachineDetailPage = lazy(() => import('./pages/MachineDetailPage'))
const StoreLayout = lazy(() => import('./components/store/StoreLayout').then((m) => ({ default: m.StoreLayout })))
const PartsStorePage = lazy(() => import('./pages/PartsStorePage'))
const PartDetailPage = lazy(() => import('./pages/PartDetailPage'))
const PartsIntelligencePage = lazy(() => import('./pages/PartsIntelligencePage'))
const CheckoutPage = lazy(() => import('./pages/CheckoutPage'))
const CommercePage = lazy(() => import('./pages/CommercePage'))
const AgenticShoppingPage = lazy(() => import('./pages/AgenticShoppingPage'))
const LegalPage = lazy(() => import('./pages/LegalPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))
const SignInPage = lazy(() => import('./pages/SignInPage'))
const OrdersPage = lazy(() => import('./pages/OrdersPage'))
const OrderDetailPage = lazy(() => import('./pages/OrderDetailPage'))
const PartsServicesPage = lazy(() => import('./pages/PartsServicesPage'))

/** End users and visitors use the one Agentic E-Commerce screen (Agentic Shopping); the assistant screen is the order processor's workspace. Bookmarks keep working. */
function CommerceRoute() {
  const { user, ready } = useSession()
  const { search } = useLocation()
  if (!ready) return null
  return user?.role === 'ORDER_PROCESSOR' ? <CommercePage /> : <Navigate to={`/agentic-shopping${search}`} replace />
}

function AgentRedirect() {
  const { search } = useLocation()
  return <Navigate to={`/agentic-shopping${search}`} replace />
}

export default function App() {
  return (
    <SessionProvider>
    <Suspense fallback={null}>
      <Routes>
        <Route element={<SiteLayout />}>
          <Route index element={<HomePage />} />
          <Route path="parts-services" element={<PartsServicesPage />} />
          <Route path="machines" element={<MachinesPage />} />
          <Route path="machines/:model" element={<MachineDetailPage />} />
          <Route path="parts-store" element={<StoreLayout />}>
            <Route index element={<PartsStorePage />} />
            <Route path="checkout" element={<CheckoutPage />} />
            <Route path="agent" element={<AgentRedirect />} />
            <Route path=":partNo" element={<PartDetailPage />} />
          </Route>
          <Route path="commerce" element={<CommerceRoute />} />
          <Route path="agentic-shopping" element={<AgenticShoppingPage />} />
          <Route path="parts-intelligence" element={<PartsIntelligencePage />} />
          <Route path="sign-in" element={<SignInPage />} />
          <Route path="orders" element={<OrdersPage />} />
          <Route path="orders/:orderId" element={<OrderDetailPage />} />
          <Route path="legal" element={<LegalPage kind="legal" />} />
          <Route path="privacy" element={<LegalPage kind="privacy" />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
    </SessionProvider>
  )
}
