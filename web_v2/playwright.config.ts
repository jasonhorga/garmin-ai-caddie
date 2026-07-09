import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  timeout: 60_000,
  fullyParallel: true,
  // Memory guardrail: this is a small (2GB) box. Cap to one worker so at most one
  // chromium page is alive at a time, and two test files never run in parallel.
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Record every e2e flow as a real screen video (the history-visual walk is the web demo). Written to
    // test-results/<test>/video.webm; CI uploads them, and ffmpeg → mp4 for delivery.
    video: 'on',
  },
  // Two dev servers: the default (:5174) is the owner/homeserver deployment
  // (no link gate); :5175 sets VITE_AI_CADDIE_REQUIRE_LINK so the multiplayer
  // isolation spec can exercise the player-facing "needs a valid link" gate
  // (multiplayer-isolation.spec.ts pins that baseURL per describe). Keeping them
  // separate leaves the existing W4a smoke walk on the ungated :5174 untouched.
  webServer: [
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',
      url: 'http://127.0.0.1:5174',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5175 --strictPort',
      url: 'http://127.0.0.1:5175',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { ...process.env, VITE_AI_CADDIE_REQUIRE_LINK: 'true' },
    },
  ],
  projects: [
    {
      name: 'desktop-chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 980 } },
    },
    {
      name: 'mobile-chromium',
      use: { ...devices['Pixel 7'] },
    },
  ],
})
