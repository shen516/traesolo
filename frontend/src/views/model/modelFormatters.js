/**
 * 模型管理页共用纯格式化函数（无状态，可单测）。
 */

import { formatDate, formatDateTimeSec } from '@/utils/formatters'

// 日期格式化统一来自 utils/formatters.js，并保持本模块既有导出名兼容
export { formatDate }

export const LEAGUE_NAME_MAP = {
  EPL: '英超',
  LALIGA: '西甲',
  BUNDES: '德甲',
  SERIEA: '意甲',
  LIGUE1: '法甲',
  UCL: '欧冠',
  UEL: '欧联杯',
  ECH: '英冠',
  WC: '世界杯',
  EC: '欧洲杯',
  CA: '美洲杯',
  AFC: '亚洲杯',
  ACN: '非洲杯',
  NOR: '挪超',
  K1: '韩职',
  MLS: '美职联',
  BRA: '巴甲',
  SWE: '瑞典超',
  FIN: '芬超',
}

export const PRIORITY_LEAGUE_ORDER = ['EPL', 'LALIGA', 'BUNDES', 'SERIEA', 'LIGUE1', 'UCL', 'UEL', 'WC']

export function leagueName(id) {
  return LEAGUE_NAME_MAP[id] || id
}

export function formatTrendDate(dateStr) {
  if (!dateStr) return ''
  const parts = String(dateStr).split('T')[0].split(' ')[0].split('-')
  if (parts.length >= 3) return `${parts[1]}-${parts[2]}`
  return dateStr
}

/** 模型任务时间展示含秒；空值显示 '-' */
export function formatDateTime(dateStr) {
  return formatDateTimeSec(dateStr, '-')
}

export function formatRange(start, end) {
  if (!start && !end) return '-'
  return `${formatDate(start) || '?'} ~ ${formatDate(end) || '?'}`
}

export function formatAccuracy(val) {
  if (val == null || val === '') return '-'
  const n = Number(val)
  if (Number.isNaN(n)) return '-'
  const pct = n <= 1 ? n * 100 : n
  return pct.toFixed(1) + '%'
}

export function formatSmoothAlpha(val) {
  if (val == null || val === '') return '—'
  const n = Number(val)
  if (Number.isNaN(n)) return '—'
  return n.toFixed(2)
}

export function formatPoissonHa(v) {
  if (v == null || v === '') return '-'
  const n = Number(v)
  if (Number.isNaN(n)) return '-'
  return n.toFixed(2)
}

export function formatDuration(ms) {
  if (!ms && ms !== 0) return '-'
  if (ms < 1000) return ms + 'ms'
  const s = ms / 1000
  if (s < 60) return s.toFixed(1) + 's'
  return Math.floor(s / 60) + 'm ' + Math.round(s % 60) + 's'
}

export function weightPct(w) {
  if (w == null) return '-'
  return Math.round(Number(w) * 100) + '%'
}

export function accuracyColor(pct) {
  if (pct == null || Number.isNaN(pct)) return 'var(--text-muted)'
  if (pct >= 60) return 'var(--color-green)'
  if (pct >= 50) return 'var(--color-blue)'
  if (pct >= 40) return 'var(--color-gold)'
  return 'var(--color-orange)'
}

export function statusTag(status) {
  return { success: 'tag-low', failed: 'tag-high', running: 'tag-info' }[status] || 'tag-mid'
}

export function statusText(status) {
  return { success: '成功', failed: '失败', running: '进行中' }[status] || status
}

export function priorityTag(p) {
  return { high: 'tag-high', mid: 'tag-mid', low: 'tag-low' }[p] || 'tag-mid'
}

export function priorityText(p) {
  return { high: '高优先', mid: '中优先', low: '低优先' }[p] || p
}

export function leagueSourceTag(source) {
  return {
    league: 'tag-low',
    league_blended: 'tag-info',
    global_better: 'tag-info',
    global_fallback: 'tag-mid',
    runtime: 'tag-mid',
  }[source] || 'tag-mid'
}

export function leagueSourceText(source) {
  return {
    league: '联赛优化',
    league_blended: '小样本混合',
    global_better: '全局更优',
    global_fallback: '全局回退',
    runtime: '运行时',
    unknown: '未知',
  }[source] || source || '-'
}

export function driftStatusText(status) {
  return { stable: '稳定', improved: '提升', degraded: '退化', unknown: '未知' }[status] || status || '-'
}

export function driftStatusClass(status) {
  return {
    stable: 'status-stable',
    improved: 'status-improved',
    degraded: 'status-degraded',
    unknown: 'status-unknown',
  }[status] || 'status-unknown'
}

export function formatMetricPct(val) {
  if (val == null || val === '') return '-'
  const n = Number(val)
  if (Number.isNaN(n)) return '-'
  return (n <= 1 ? n * 100 : n).toFixed(1) + '%'
}

export function formatMetricNum(val) {
  if (val == null || val === '') return '-'
  const n = Number(val)
  if (Number.isNaN(n)) return '-'
  return n.toFixed(4)
}

export function formatDrift(val) {
  if (val == null || val === '') return '-'
  const n = Number(val)
  if (Number.isNaN(n)) return '-'
  const pct = (n <= 1 && n >= -1 ? n * 100 : n).toFixed(1)
  return (n > 0 ? '+' : '') + pct + '%'
}

/** 解析后端返回的 weights_json（字符串或对象） */
export function parseWeightsJson(raw) {
  if (!raw) return null
  if (typeof raw === 'object') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/** by_league 兼容 {EPL: {weights,...}} 与旧 {EPL: {elo,poisson,...}} 两种结构 */
export function normalizeByLeagueMap(raw) {
  if (!raw || typeof raw !== 'object') return {}
  const out = {}
  for (const [lid, meta] of Object.entries(raw)) {
    if (!meta || typeof meta !== 'object') continue
    if (meta.weights && typeof meta.weights === 'object') {
      out[lid] = meta
    } else if (['elo', 'poisson', 'xg', 'monte_carlo'].some(k => k in meta)) {
      out[lid] = { weights: meta, source: 'runtime' }
    }
  }
  return out
}
