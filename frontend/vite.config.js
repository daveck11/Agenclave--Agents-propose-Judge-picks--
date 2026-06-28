import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev-server proxy: forward API calls to the FastAPI service on :8000 so the
// app can use relative fetch URLs (/triage, /health) without CORS config.
// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/triage': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/runs': 'http://localhost:8000',
    },
  },
})
