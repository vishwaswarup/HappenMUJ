import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server proxies /api to the FastAPI backend so the browser never needs CORS in development.
// loadEnv reads .env files AND the shell environment, so VITE_PROXY_TARGET works from either
// (plain process.env would ignore .env, because Vite only exposes .env values to client code).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': { target: env.VITE_PROXY_TARGET || 'http://localhost:8000', changeOrigin: true },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['tests/**/*.test.{ts,tsx}'],
      setupFiles: ['tests/setup.ts'],
      // The suite is written against the built-in sample data: never let a developer's .env (which may point
      // VITE_API_BASE_URL at a real backend) change which adapter the tests use.
      env: { VITE_API_BASE_URL: '' },
    },
  };
});
