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
    watch: { ignored: ['**/.export-check-*/**'] },
  },
  // Export verification has its own root and runner. Never discover its
  // temporary files as part of the Studio's component suite.
  test: { exclude: ['**/node_modules/**', '**/.export-check-*/**'] },
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
