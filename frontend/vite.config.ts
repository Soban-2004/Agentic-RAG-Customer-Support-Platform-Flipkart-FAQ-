import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev-server proxy to the FastAPI backend -- keeps the browser's view of
// everything same-origin (localhost:5173), so there's no CORS/cross-origin
// cookie handling to reason about at all. In prod, FastAPI serves this app's
// built output directly (see main.py), so the proxy is dev-only.
export default defineConfig({
  // VITE_BASE_PATH lets the production image live below a shared host path
  // while local development keeps the usual root URL.
  base: process.env.VITE_BASE_PATH || '/',
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true, changeOrigin: true },
    },
  },
})
