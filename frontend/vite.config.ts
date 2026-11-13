import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { port: mode === 'e2e' ? 5174 : 5173, strictPort: true, proxy: { '/api': mode === 'e2e' ? 'http://127.0.0.1:8001' : 'http://127.0.0.1:8000' } },
}))
