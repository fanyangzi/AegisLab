import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: {
    // The previous console is retained for migration, not shown in new navigation.
    rollupOptions: { input: { main: new URL('index.html', import.meta.url).pathname, legacy: new URL('legacy.html', import.meta.url).pathname } },
  },
})
