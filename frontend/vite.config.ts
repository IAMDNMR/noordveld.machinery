import { resolve } from 'node:path'
import type { Connect } from 'vite'
import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

/** `/agentic-commerce` → `/agentic-commerce/`, so the folder's own index.html is served. */
const agenticSlash: Connect.NextHandleFunction = (req, res, next) => {
  if (req.url === '/agentic-commerce' || req.url?.startsWith('/agentic-commerce?')) {
    res.statusCode = 301
    res.setHeader('Location', req.url.replace('/agentic-commerce', '/agentic-commerce/'))
    res.end()
    return
  }
  next()
}

const agenticRedirect = (): Plugin => ({
  name: 'agentic-trailing-slash',
  configureServer: (server) => void server.middlewares.use(agenticSlash),
  configurePreviewServer: (server) => void server.middlewares.use(agenticSlash),
})

// Two pages in one site: the Noordveld website (/) and the Agentic E-Commerce introduction (/agentic-commerce/).
export default defineConfig({
  plugins: [react(), agenticRedirect()],
  // The Parts Store reads the catalogue from the FastAPI backend (backend/, port 8000)
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
  // Long conversation tests wait on several async steps; a fully loaded parallel run needs more than the defaults.
  test: { testTimeout: 20000, setupFiles: ['./src/test-setup.ts'] },
  preview: { proxy: { '/api': 'http://localhost:8000' } },
  build: {
    target: 'es2022',
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, 'index.html'),
        agentic: resolve(import.meta.dirname, 'agentic-commerce/index.html'),
      },
    },
  },
})
