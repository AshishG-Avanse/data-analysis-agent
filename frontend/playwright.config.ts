import { defineConfig, devices } from '@playwright/test'

// Test files live at the repo-root `tests/e2e/` (one level up from `frontend/`,
// where this config and `package.json` live) per spec/roadmap.md's file layout.
export default defineConfig({
  testDir: '../tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:8001',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
