import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  workers: 1,
  timeout: 45_000,
  use: {
    baseURL: 'http://127.0.0.1:5174',
    browserName: 'chromium',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {},
    trace: 'retain-on-failure',
  },
  webServer: [
    { command: '../.venv/bin/python ../scripts/e2e_backend.py', url: 'http://127.0.0.1:8001/api/health', reuseExistingServer: false },
    { command: 'npm run dev -- --mode e2e', url: 'http://127.0.0.1:5174', reuseExistingServer: false },
  ],
})
