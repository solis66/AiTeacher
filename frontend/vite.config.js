import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      // 代理所有API请求到后端
      '/chat': {
        target: 'http://localhost:8501',
        changeOrigin: true
      },
      '/login': {
        target: 'http://localhost:8501',
        changeOrigin: true
      },
      '/get_history': {
        target: 'http://localhost:8501',
        changeOrigin: true
      },
      '/save_history': {
        target: 'http://localhost:8501',
        changeOrigin: true
      },
      '/delete_history': {
        target: 'http://localhost:8501',
        changeOrigin: true
      },
      '/ocr': {
        target: 'http://localhost:8501',
        changeOrigin: true
      },
      '/health': {
        target: 'http://localhost:8501',
        changeOrigin: true
      },
      // 批改工作台接口（创建/详情/列表/保存/页面图片/导出/重试/删除）
      '/api': {
        target: 'http://localhost:8501',
        changeOrigin: true
      }
    }
  }
})