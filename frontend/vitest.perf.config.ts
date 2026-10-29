// UI rendering timings (src/**/*.perf.tsx): run on demand with `npm run perf:ui`, never as part of `npm test`.
import { defineConfig, mergeConfig } from 'vitest/config'
import base from './vite.config'

export default mergeConfig(base, defineConfig({ test: { include: ['src/**/*.perf.tsx'] } }))
