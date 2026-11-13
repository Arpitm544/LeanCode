import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  server: { port: mode === 'e2e' ? 5174 : 5173, strictPort: true, proxy: { '/api': mode === 'e2e' ? 'http://127.0.0.1:8001' : 'http://127.0.0.1:8000' } },
}))
