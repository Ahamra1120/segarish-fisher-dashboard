import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev server proxies /api and /ws to the backend so `npm run dev` works
// standalone without CORS juggling; production serves this build as
// static files straight from the backend (see backend/app.py).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
