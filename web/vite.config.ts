import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBase = env.VITE_API_BASE || 'http://localhost:8000'

  return {
    plugins: [
      vue(),
      // Element Plus 按需导入：自动导入组件与 Vue/VueRouter/Pinia 相关 API
      AutoImport({
        imports: ['vue', 'vue-router', 'pinia'],
        resolvers: [ElementPlusResolver()],
        dts: 'src/auto-imports.d.ts',
      }),
      Components({
        resolvers: [ElementPlusResolver()],
        dts: 'src/components.d.ts',
      }),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      open: false,
      proxy: {
        // 前端以 /api 开头的请求代理到后端（后端接口统一挂在 /api 前缀下，无需 rewrite）
        '/api': {
          target: apiBase,
          changeOrigin: true,
        },
        // WebSocket 代理（实时日志 / 服务器监控）
        '/ws': {
          target: apiBase,
          changeOrigin: true,
          ws: true,
        },
      },
    },
  }
})
