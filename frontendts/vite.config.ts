import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@mundi/ee': path.resolve(__dirname, './src/lib/ee-stub.tsx'),
    },
    dedupe: ['react', 'react-dom'],
  },
  base: '/',
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', ws: true, changeOrigin: true },
    },
  },
  build: {
    sourcemap: mode === 'development',
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          ui: ['@radix-ui/react-dialog', '@radix-ui/react-dropdown-menu'],
        },
      },
    },
  },
  optimizeDeps: {
    include: ['react-router-dom'],
  },
}))
