import { lazy, Suspense, useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { SiteLayout } from './components/SiteLayout'
import { SPARK_CHAT_ROUTE } from './data/content'
import { HomePage } from './pages/HomePage'
import { SessionProvider, useSession } from './store/session'

// Secondary routes load on demand to keep the first bundle small
// The main sections are fetched in the background once the first page has loaded, so moving between them is instant.
const PRIMARY = {
  machines: () => import('./pages/MachinesPage'),
  aftersales: () => import('./pages/PartsServicesPage'),
  store: () => import('./pages/PartsStorePage'),
  sparkIntro: () => import('./pages/SparkLandingPage'),
  spark: () => import('./pages/SparkPage'),
}
function PrefetchRoutes() {
  useEffect(() => {
    const idle = window.requestIdleCallback ?? ((run: () => void) => window.setTimeout(run, 1500))
    const slow = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection
      ?.saveData
    if (slow) return
    const id = idle(() =>
      Object.values(PRIMARY).forEach((load) => void load().catch(() => undefined)),
    )
    return () => (window.cancelIdleCallback ?? window.clearTimeout)(id as number)
  }, [])
  return null
}
const MachinesPage = lazy(PRIMARY.machines)
const MachineDetailPage = lazy(() => import('./pages/MachineDetailPage'))
const StoreLayout = lazy(() =>
  import('./components/store/StoreLayout').then((m) => ({ default: m.StoreLayout })),
)
const PartsStorePage = lazy(PRIMARY.store)
const PartDetailPage = lazy(() => import('./pages/PartDetailPage'))
const AftersalesPage = lazy(PRIMARY.aftersales)
const CheckoutPage = lazy(() => import('./pages/CheckoutPage'))
const CommercePage = lazy(() => import('./pages/CommercePage'))
const SparkPage = lazy(PRIMARY.spark)
const SparkLandingPage = lazy(PRIMARY.sparkIntro)
const LegalPage = lazy(() => import('./pages/LegalPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))
const SignInPage = lazy(() => import('./pages/SignInPage'))
const InvitationPage = lazy(() => import('./pages/InvitationPage'))
const OrdersPage = lazy(() => import('./pages/OrdersPage'))
const OrderDetailPage = lazy(() => import('./pages/OrderDetailPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const WorkspacePage = lazy(() => import('./pages/WorkspacePage'))
const PartsServicesPage = lazy(PRIMARY.aftersales)

/** End users and visitors use Spark; the assistant screen is the order processor's workspace. Bookmarks keep working. */
function CommerceRoute() {
  const { user, ready } = useSession()
  const { search } = useLocation()
  if (!ready) return null
  return user?.role === 'ORDER_PROCESSOR' ? (
    <CommercePage />
  ) : (
    <Navigate to={`${SPARK_CHAT_ROUTE}${search}`} replace />
  )
}

/** Earlier conversation URLs (Agentic Shopping, Parts Intelligence) keep their question, part and tab. */
function ToSparkChat() {
  const { search } = useLocation()
  return <Navigate to={`${SPARK_CHAT_ROUTE}${search}`} replace />
}

export default function App() {
  return (
    <SessionProvider>
      <PrefetchRoutes />
      <Suspense
        fallback={
          <div className="page-loading" role="status">
            <span aria-hidden="true" />
            Loading your workspace...
          </div>
        }
      >
        <Routes>
          <Route element={<SiteLayout />}>
            <Route index element={<HomePage />} />
            <Route path="parts-services" element={<PartsServicesPage />} />
            <Route path="machines" element={<MachinesPage />} />
            <Route path="machines/:model" element={<MachineDetailPage />} />
            <Route path="parts-store" element={<StoreLayout />}>
              <Route index element={<PartsStorePage />} />
              <Route path="checkout" element={<CheckoutPage />} />
              <Route path="agent" element={<ToSparkChat />} />
              <Route path=":partNo" element={<PartDetailPage />} />
            </Route>
            <Route path="commerce" element={<CommerceRoute />} />
            <Route path="spark" element={<SparkLandingPage />} />
            <Route path="spark/chat" element={<SparkPage />} />
            <Route path="agentic-commerce/*" element={<SparkLandingPage />} />
            <Route path="agentic-shopping" element={<ToSparkChat />} />
            <Route path="parts-intelligence" element={<ToSparkChat />} />
            <Route path="aftersales" element={<AftersalesPage />} />
            <Route path="parts-services" element={<Navigate to="/aftersales" replace />} />
            <Route path="sign-in" element={<SignInPage />} />
            <Route path="invite" element={<InvitationPage />} />
            <Route path="orders" element={<OrdersPage />} />
            <Route path="orders/:orderId" element={<OrderDetailPage />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="workspace" element={<WorkspacePage />} />
            <Route path="legal" element={<LegalPage kind="legal" />} />
            <Route path="privacy" element={<LegalPage kind="privacy" />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </SessionProvider>
  )
}
