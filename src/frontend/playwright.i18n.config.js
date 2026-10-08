import { defineConfig } from '@playwright/test'

// Interface-only fixtures: no real instance, credentials or agent mutations.
export default defineConfig({
  testDir: './tests/browser',
  testMatch: 'i18n.spec.js',
  outputDir: 'e2e/test-results/i18n',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5173',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: !process.env.CI,
  },
})
