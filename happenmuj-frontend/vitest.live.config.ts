import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Opt-in end-to-end run: the real React app + the real HTTP adapter against a RUNNING backend (seeded).
//   LIVE_API=http://localhost:8000/api npm run test:live
// It creates data (an event, a comment), so re-seed afterwards for a pristine demo. jsdom, not a real browser.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    environmentOptions: { jsdom: { url: 'http://localhost:5173/' } },
    globals: true,
    include: ['tests/live/**/*.live.tsx'],
    setupFiles: ['tests/setup.ts'],
    testTimeout: 60_000,
    fileParallelism: false,
    env: { VITE_API_BASE_URL: process.env.LIVE_API ?? 'http://localhost:8000/api' },
  },
});
