import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import type { ApplicationDefinition } from '../api/applicationDefinition'
import { BrandMark } from '../components/BrandMark'
import { ApplicationPreview } from '../components/studio/views/ApplicationPreview'
import snapshot from '../assets/studio/demo-application.json'
import './StudioDemoPage.css'

// Curated synthetic reference design. No accounts, operational records,
// approval identities, customer integrations or API calls enter this viewer.
const definition = snapshot as unknown as ApplicationDefinition

export default function StudioDemoPage() {
  return (
    <div className="studio-demo">
      <header className="studio-demo__header">
        <Link to="/design-studio" className="studio-demo__brand">
          <BrandMark />
          <strong>Design Studio</strong>
        </Link>
        <span>
          Transport Operations <small>Interactive design demo</small>
        </span>
        <Link to="/design-studio">
          <ArrowLeft size={15} /> Open Design Studio
        </Link>
      </header>
      <p className="studio-demo__note">
        Explore a transport workflow, from shipment planning to delivery.
      </p>
      <ApplicationPreview definition={definition} viewport="desktop" />
    </div>
  )
}
