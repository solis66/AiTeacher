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
      // 注册接口：后端 /register（LoginPage 注册模式调用）
      // 此前漏配，请求会落到 vite 自己身上、返回 index.html，导致注册一直失败
      '/register': {
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
      // 配置自检接口（后端 /config/check，排查密钥/模型问题用）
      '/config': {
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