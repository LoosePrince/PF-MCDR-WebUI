import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  base: '',
  build: {
    outDir: '../static',
    emptyOutDir: true,
    // 路由已懒加载，主包已拆分；vendor 单库体积较大时放宽告警阈值
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // 懒加载页面：按路径命名，避免 [hash]
          const pageMatch = id.match(/[/\\]pages[/\\]([^/\\]+)\.(tsx|jsx|ts|js)(\?|$)/);
          if (pageMatch) {
            return pageMatch[1];
          }
          // React Flow 拓扑图库（需先于 react 规则，@xyflow/react 路径含 "react" 子串）
          if (id.includes('@xyflow') || id.includes('reactflow')) {
            return 'reactflow-vendor';
          }
          // React 核心库
          if (id.includes('react') || id.includes('react-dom') || id.includes('react-router-dom')) {
            return 'react-vendor';
          }
          // i18n 相关
          if (id.includes('i18next') || id.includes('react-i18next')) {
            return 'i18n-vendor';
          }
          // CodeMirror 相关（较大的库）
          if (id.includes('@uiw/react-codemirror') || id.includes('@codemirror')) {
            return 'codemirror-vendor';
          }
          // framer-motion 动画库
          if (id.includes('framer-motion')) {
            return 'framer-motion-vendor';
          }
          // axios
          if (id.includes('axios')) {
            return 'axios-vendor';
          }
          // lucide-react 图标库
          if (id.includes('lucide-react')) {
            return 'lucide-vendor';
          }
          // recharts 图表库及其 d3 依赖
          if (id.includes('recharts') || id.includes('/d3-') || id.includes('victory-vendor')) {
            return 'recharts-vendor';
          }
        },
        // 固定输出文件名，去掉随机哈希
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
