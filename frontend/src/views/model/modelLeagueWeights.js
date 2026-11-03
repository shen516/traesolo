/**
 * 分联赛权重表行的纯构建逻辑（Training tab 与详情弹窗共用）。
 */
import { MODEL_COLORS } from '@/utils/chartTheme'
import { LEAGUE_NAME_MAP, PRIORITY_LEAGUE_ORDER, parseWeightsJson, normalizeByLeagueMap } from './modelFormatters'

export const WEIGHT_SEGMENT_META = [
  { key: 'elo', label: 'ELO', color: MODEL_COLORS.elo },
  { key: 'poisson', label: '泊松', color: MODEL_COLORS.poisson },
  { key: 'xg', label: 'xG', color: MODEL_COLORS.xg },
  { key: 'monte_carlo', label: '蒙特卡洛', color: MODEL_COLORS.monte_carlo },
]

export function buildLeagueRows(byLeagueMap) {
  const rows = Object.entries(byLeagueMap || {}).map(([id, meta]) => {
    const weights = {
      elo: Number(meta.weights?.elo ?? meta.elo ?? 0),
      poisson: Number(meta.weights?.poisson ?? meta.poisson ?? 0),
      xg: Number(meta.weights?.xg ?? meta.xg ?? 0),
      monte_carlo: Number(meta.weights?.monte_carlo ?? meta.monte_carlo ?? 0),
    }
    const total = Object.values(weights).reduce((s, v) => s + (v > 0 ? v : 0), 0) || 1
    const segments = WEIGHT_SEGMENT_META.map(m => ({
      ...m,
      pct: Math.round((Math.max(0, weights[m.key]) / total) * 100),
    })).filter(s => s.pct > 0)
    const accuracy = meta.validation_accuracy
    let accuracyPct = null
    if (accuracy != null && accuracy !== '') {
      const n = Number(accuracy)
      accuracyPct = n <= 1 ? n * 100 : n
    }
    return {
      id,
      name: LEAGUE_NAME_MAP[id] || '',
      source: meta.source || 'unknown',
      hyperSource: meta.hyper_source || meta.hyperSource || null,
      trainMatches: meta.train_matches ?? meta.sample_n ?? null,
      validationMatches: meta.validation_matches ?? null,
      accuracy: accuracy != null ? Number(accuracy) : null,
      accuracyPct,
      smoothAlpha: meta.smooth_alpha != null ? Number(meta.smooth_alpha) : null,
      weights,
      hyperparams: meta.hyperparams || null,
      segments,
      priority: PRIORITY_LEAGUE_ORDER.indexOf(id),
    }
  })
  rows.sort((a, b) => {
    const ap = a.priority >= 0 ? a.priority : 99
    const bp = b.priority >= 0 ? b.priority : 99
    if (ap !== bp) return ap - bp
    const aa = a.accuracyPct ?? -1
    const ba = b.accuracyPct ?? -1
    return ba - aa
  })
  return rows
}

export { parseWeightsJson, normalizeByLeagueMap }
