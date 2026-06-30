/// <reference types="vitest" />

import react from '@vitejs/plugin-react'
import type { Plugin } from 'vite'
import { loadEnv } from 'vite'
import { configDefaults, defineConfig } from 'vitest/config'
import { assertNoConsumerAdminToken } from './src/buildGuards'

// SECURITY: fail `vite build` if a consumer/public build (VITE_AI_CADDIE_REQUIRE_LINK=true)
// would bake the owner admin token (VITE_AI_CADDIE_DEFAULT_ADMIN_TOKEN) into the shipped JS.
// `apply: 'build'` keeps it out of dev (`npm run dev`) and vitest, so only real builds are gated.
function consumerAdminTokenGuard(): Plugin {
  return {
    name: 'ai-caddie:no-consumer-admin-token',
    apply: 'build',
    config(_config, { mode }) {
      // loadEnv (empty prefix) returns BOTH .env-file values AND process.env vars, so
      // this catches the flags however a deploy/CI sets them. '.' is web_v2 at build time.
      const env = loadEnv(mode, '.', '')
      assertNoConsumerAdminToken({
        bakedAdminToken: env.VITE_AI_CADDIE_DEFAULT_ADMIN_TOKEN,
        requireLink: env.VITE_AI_CADDIE_REQUIRE_LINK,
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), consumerAdminTokenGuard()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
})
