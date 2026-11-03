import axios from 'axios'

/** 默认相对路径：开发走 Vite 代理，Docker 走 Nginx 同域反代；可用 VITE_API_BASE_URL 覆盖 */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器 - 自动携带Token
request.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

// 响应拦截器 - 统一错误处理
let redirectingToLogin = false

request.interceptors.response.use(
  response => response.data,
  error => {
    if (error.response) {
      const { status, data } = error.response
      if (status === 401) {
        const reqUrl = error.config?.url || ''
        const isAuthEndpoint = /\/auth\/(login|captcha)/.test(reqUrl)

        localStorage.removeItem('token')
        localStorage.removeItem('user')
        localStorage.removeItem('roles')
        localStorage.removeItem('permissions')

        const onLoginPage = window.location.pathname === '/login'
        if (!isAuthEndpoint && !onLoginPage && !redirectingToLogin) {
          redirectingToLogin = true
          // 动态 import 避免 api ↔ router ↔ store 循环依赖
          import('@/router').then(({ default: router }) => {
            const redirect = router.currentRoute.value?.fullPath
            return router.replace({
              path: '/login',
              query: redirect && redirect !== '/' && redirect !== '/login'
                ? { redirect }
                : undefined,
            })
          }).finally(() => {
            setTimeout(() => { redirectingToLogin = false }, 800)
          })
        }
        return Promise.reject(new Error(isAuthEndpoint
          ? (data?.detail || data?.message || '登录失败')
          : '登录已过期，请重新登录'))
      }
      // 403 是权限门控，不是登录失效：不触发"请重新登录"，否则强制改密页会循环跳回登录。
      // 强制改密的 detail 是对象 {code, message}，用 message 更准确。
      if (status === 403) {
        const d = data?.detail
        const msg = typeof d === 'object' && d !== null
          ? (d.message || '无权限访问该功能')
          : (d || '无权限访问该功能')
        const err = new Error(msg)
        err.code = typeof d === 'object' && d !== null ? d.code : null
        return Promise.reject(err)
      }
      // 422 校验失败的 detail 是数组：[{loc, msg, type}]，需展开为可读文案
      // 订阅门控的 detail 是对象：{code: 'FEATURE_LOCKED', feature, message}
      const detail = data?.detail
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        const err = new Error(detail.message || data?.message || '请求失败')
        err.code = detail.code
        err.feature = detail.feature
        return Promise.reject(err)
      }
      const msg = Array.isArray(detail)
        ? detail.map(d => d?.msg || JSON.stringify(d)).join('；')
        : (detail || data?.message || '请求失败')
      return Promise.reject(new Error(msg))
    }
    return Promise.reject(new Error('网络异常，请检查后端服务是否启动'))
  }
)

export default request
