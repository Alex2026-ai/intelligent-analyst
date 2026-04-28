import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  // Load env files based on mode (.env, .env.local, .env.[mode], etc.)
  const env = loadEnv(mode, process.cwd(), '');

  // Backend proxy targets are local/placeholders by default for public clones.
  const BACKEND_URL = env.VITE_API_BASE_URL || 'http://localhost:8080';
  const PMC_BACKEND_URL = env.VITE_PMC_API_URL || BACKEND_URL;

  console.log(`[vite] Proxy target: ${BACKEND_URL}`);
  console.log(`[vite] PMC proxy target: ${PMC_BACKEND_URL}`);

  return {
  plugins: [react()],
  base: '/',
  build: {
    outDir: 'dist',
  },
  server: {
    port: 5173,
    proxy: {
      // PMC public feed — /v1/public-metadata/* → ia-api (separate service)
      '/v1/public-metadata': {
        target: PMC_BACKEND_URL,
        changeOrigin: true,
        secure: true,
      },
      // Dashboard proxy /api/* → backend root (strips /api prefix)
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  };
});
