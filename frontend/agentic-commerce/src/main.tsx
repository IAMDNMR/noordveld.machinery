import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import '../../src/styles/tokens.css'
import '../../src/styles/base.css'

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
