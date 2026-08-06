import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发服务器：host 0.0.0.0 方便手机同网访问；/api 反代到 FastAPI
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
