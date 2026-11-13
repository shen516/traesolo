/**
 * 全局统一的日期/时间格式化函数（纯函数，可单测）。
 *
 * 约定：
 * - 空输入返回 fallback（默认空字符串）；
 * - 字符串日期优先做字符串截取（避免时区偏移），非字符串才走 Date 解析；
 * - 解析失败返回 fallback。
 */

/** 格式化日期为 YYYY-MM-DD */
export function formatDate(d, fallback = '') {
  if (!d) return fallback
  if (typeof d === 'string') return d.slice(0, 10)
  try {
    const dt = new Date(d)
    if (isNaN(dt.getTime())) return fallback
    const y = dt.getFullYear()
    const m = String(dt.getMonth() + 1).padStart(2, '0')
    const day = String(dt.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  } catch {
    return fallback
  }
}

/** 格式化时间为 HH:MM（截取字符串前 5 位） */
export function formatTime(t, fallback = '') {
  if (!t) return fallback
  return String(t).slice(0, 5)
}

/** 格式化日期时间为 YYYY-MM-DD HH:MM */
export function formatDateTime(dt, fallback = '') {
  if (!dt) return fallback
  try {
    const date = new Date(dt)
    if (isNaN(date.getTime())) return fallback
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const h = String(date.getHours()).padStart(2, '0')
    const min = String(date.getMinutes()).padStart(2, '0')
    return `${y}-${m}-${day} ${h}:${min}`
  } catch {
    return fallback
  }
}

/** 格式化日期时间为 YYYY-MM-DD HH:MM:SS（含秒，用于训练任务/日志等场景） */
export function formatDateTimeSec(dt, fallback = '') {
  if (!dt) return fallback
  try {
    const date = new Date(dt)
    if (isNaN(date.getTime())) return fallback
    const base = formatDateTime(date, '')
    if (!base) return fallback
    const s = String(date.getSeconds()).padStart(2, '0')
    return `${base}:${s}`
  } catch {
    return fallback
  }
}

/** 紧凑格式 M-D HH:MM（月/日不补零，用于日志文件列表、最近登录等场景） */
export function formatCompactDateTime(dt, fallback = '-') {
  if (!dt) return fallback
  try {
    const d = new Date(dt)
    if (isNaN(d.getTime())) return fallback
    return `${d.getMonth() + 1}-${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return fallback
  }
}
