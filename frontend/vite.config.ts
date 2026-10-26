import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig, type ProxyOptions } from 'vite'

import { mockDbPlugin } from './vite.mock-plugin'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: mode === 'mock' ? [vue(), mockDbPlugin()] : [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // mock 模式下不代理后端:全部流量走前端自身
    proxy:
      mode === 'mock'
        ? undefined
        : ({
            // REST 接口转发到后端(契约见 docs/02-API约定.md)
            '/api': {
              target: 'http://127.0.0.1:8000',
              changeOrigin: true,
            },
            // WebSocket 推送通道
            '/ws': {
              target: 'ws://127.0.0.1:8000',
              ws: true,
            },
          } satisfies Record<string, string | ProxyOptions>),
  },
}))
