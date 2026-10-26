import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The API runs on :8000. Proxying keeps the browser on one origin, so dev needs no CORS setup
    proxy: {
      '/api': { target: 'http://localhost:8000', rewrite: (path) => path.replace(/^\/api/, '') },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
