/** 媒体根：空串表示同域（Vite 代理 / Docker Nginx）；可用 VITE_API_ORIGIN 覆盖 */
const API_ORIGIN = (import.meta.env.VITE_API_ORIGIN || '').replace(/\/$/, '')

export function isMediaSrc(src) {
  if (!src || typeof src !== 'string') return false
  return src.startsWith('http://') || src.startsWith('https://') || src.startsWith('/static/')
}

export function mediaUrl(src) {
  if (!isMediaSrc(src)) return ''
  if (src.startsWith('/static/')) return API_ORIGIN + src
  return src
}
