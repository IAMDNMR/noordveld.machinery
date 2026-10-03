import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { SiteLayout } from './components/SiteLayout'
import { HomePage } from './pages/HomePage'

// Secondary routes load on demand to keep the first bundle small
const MachinesPage = lazy(() => import('./pages/MachinesPage'))
const MachineDetailPage = lazy(() => import('./pages/MachineDetailPage'))
const StoreLayout = lazy(() => import('./components/store/StoreLayout').then((m) => ({ default: m.StoreLayout })))
const PartsStorePage = lazy(() => import('./pages/PartsStorePage'))
const PartDetailPage = lazy(() => import('./pages/PartDetailPage'))
const LegalPage = lazy(() => import('./pages/LegalPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))

export default function App() {
  return (
    <Suspense fallback={null}>
      <Routes>
        <Route element={<SiteLayout />}>
          <Route index element={<HomePage />} />
          <Route path="machines" element={<MachinesPage />} />
          <Route path="machines/:model" element={<MachineDetailPage />} />
          <Route path="parts-store" element={<StoreLayout />}>
            <Route index element={<PartsStorePage />} />
            <Route path=":partNo" element={<PartDetailPage />} />
          </Route>
          <Route path="legal" element={<LegalPage kind="legal" />} />
          <Route path="privacy" element={<LegalPage kind="privacy" />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
