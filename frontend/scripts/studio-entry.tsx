import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { StudioProvider } from '@studio/sdk'
class Boundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <main role="alert">
        <h1>This application could not render</h1>
        <p>Return to Studio and regenerate with the error details.</p>
      </main>
    ) : (
      this.props.children
    )
  }
}
createRoot(document.getElementById('app')!).render(
  <Boundary>
    <StudioProvider>
      <App />
    </StudioProvider>
  </Boundary>,
)
