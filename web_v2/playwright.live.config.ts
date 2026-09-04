import { defineConfig, devices } from '@playwright/test'

// Real-player evidence has one deliberately narrow runner. Port 5173 is part of
// the deployed API's local-development CORS contract; the general E2E config's
// 5174/5175 fixture servers are intentionally not used here.
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results/live-evidence',
  timeout: 90_000,
  workers: 1,
  reporter: [['line']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...process.env,
      VITE_AI_CADDIE_REQUIRE_LINK: 'true',
    },
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 980 },
      },
    },
  ],
})
