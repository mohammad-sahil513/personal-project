import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// `loadEnv` loads .env files; BACKEND_ORIGIN / VITE_DEV_PROXY_TARGET are not exposed to the client bundle.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget =
    env.BACKEND_ORIGIN ||
    env.VITE_DEV_PROXY_TARGET ||
    'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
