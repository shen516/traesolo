import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { networkInterfaces } from 'node:os'
import { fileURLToPath, URL } from 'node:url'

/**
 * 解析后端代理地址。
 * Windows 上若另有进程独占绑定 127.0.0.1:8000，而 traesolo 监听 0.0.0.0:8000，
 * 走 127.0.0.1 会打到错误服务（验证码/登录 404）。此时改走本机非回环 IPv4。
 * 可用 VITE_API_PROXY_TARGET 覆盖，例如 http://127.0.0.1:8000
 */
function resolveBackendProxyTarget() {
  const fromEnv = (process.env.VITE_API_PROXY_TARGET || '').trim()
  if (fromEnv) return fromEnv.replace(/\/$/, '')

  const ipv4 = []
  for (const list of Object.values(networkInterfaces())) {
    for (const net of list || []) {
      const family = typeof net.family === 'number' ? net.family : String(net.family)
      const isV4 = family === 4 || family === 'IPv4'
      if (!isV4 || net.internal || !net.address) continue
      if (net.address.startsWith('169.254.')) continue
      ipv4.push(net.address)
    }
  }
  ipv4.sort((a, b) => {
    const rank = (ip) => (ip.startsWith('192.168.') ? 0 : ip.startsWith('10.') ? 1 : 2)
    return rank(a) - rank(b)
  })
  if (ipv4.length) return `http://${ipv4[0]}:8000`
  return 'http://127.0.0.1:8000'
}

const backendProxyTarget = resolveBackendProxyTarget()

/** 把后端 307 Location 改成相对路径，避免浏览器跳出 Vite 同源代理后丢掉 Authorization */
function keepRedirectOnViteOrigin() {
  return {
    configure(proxy) {
      proxy.on('proxyRes', (proxyRes) => {
        const loc = proxyRes.headers?.location
        if (!loc || typeof loc !== 'string') return
        try {
          const u = new URL(loc, backendProxyTarget)
          proxyRes.headers.location = `${u.pathname}${u.search}${u.hash}`
        } catch (_) {
          /* ignore malformed Location */
        }
      })
    },
  }
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  test: {
    environment: 'node',
    include: ['src/**/*.{test,spec}.{js,mjs}'],
  },
  server: {
    port: 5173,
    open: false,
    proxy: {
      '/api': {
        target: backendProxyTarget,
        changeOrigin: true,
        ...keepRedirectOnViteOrigin(),
      },
      '/static': {
        target: backendProxyTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          echarts: ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'],
        },
      },
    },
  },
})
