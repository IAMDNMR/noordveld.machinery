import { defineConfig, mergeConfig } from 'vite'
import base from '../vite.config.ts'

/** One review configuration; override STUDIO_WEB_PORT and STUDIO_API_TARGET for isolated runs. */
export default mergeConfig(
  base,
  defineConfig({
    server: {
      host: '127.0.0.1',
      port: Number(process.env.STUDIO_WEB_PORT ?? 5202),
      strictPort: true,
      proxy: { '/api': process.env.STUDIO_API_TARGET ?? 'http://127.0.0.1:8022' },
    },
  }),
)
