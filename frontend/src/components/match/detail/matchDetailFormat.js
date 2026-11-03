/** Pure helpers shared by MatchDetail page and its section components. */

export function toCamelCase(str) {
  return str.replace(/_([a-z])/g, (_, c) => c.toUpperCase())
}

export function convertKeys(obj) {
  if (Array.isArray(obj)) return obj.map(convertKeys)
  if (obj && typeof obj === 'object') {
    return Object.keys(obj).reduce((acc, key) => {
      acc[toCamelCase(key)] = convertKeys(obj[key])
      return acc
    }, {})
  }
  return obj
}

export function formatDate(d) {
  if (!d) return ''
  if (typeof d === 'string') return d.slice(0, 10)
  try {
    const dt = new Date(d)
    if (isNaN(dt.getTime())) return ''
    const y = dt.getFullYear()
    const m = String(dt.getMonth() + 1).padStart(2, '0')
    const day = String(dt.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  } catch {
    return ''
  }
}

export function formatTime(t) {
  if (!t) return ''
  return String(t).slice(0, 5)
}

export function formatSnapshotTime(v) {
  if (!v) return '-'
  const s = String(v)
  return s.replace('T', ' ').slice(0, 16)
}

export function stageText(stage) {
  return {
    group: '小组赛',
    round_of_16: '1/8决赛',
    quarter_final: '四分之一决赛',
    semi_final: '半决赛',
    third_place: '季军赛',
    final: '决赛',
    league: '联赛',
    qualifying: '资格赛',
    knockout: '淘汰赛',
    playoff: '附加赛',
    play_in: '附加圈',
  }[stage] || stage || ''
}

export function levelText(level) {
  return { high: '高', mid: '中', low: '低' }[level] || level || '-'
}

export function statusClass(status) {
  return {
    upcoming: 'tag tag-info',
    live: 'tag tag-low',
    finished: 'tag tag-mid',
  }[status] || 'tag tag-info'
}

export function statusText(status) {
  return {
    upcoming: '未开始',
    live: '进行中',
    finished: '已结束',
  }[status] || status
}

export function confidenceTagClass(level) {
  return {
    high: 'tag tag-low',
    mid: 'tag tag-mid',
    low: 'tag tag-high',
  }[level] || 'tag tag-info'
}

export function riskTagClass(level) {
  return {
    low: 'tag tag-low',
    mid: 'tag tag-mid',
    high: 'tag tag-high',
  }[level] || 'tag tag-info'
}

export function resultClass(result) {
  return {
    home: 'result-home',
    draw: 'result-draw',
    away: 'result-away',
  }[result] || 'result-draw'
}

export function resultText(result) {
  return {
    home: '主胜',
    draw: '平',
    away: '客胜',
  }[result] || result
}

export function positionText(pos) {
  return {
    GK: '门将', CB: '中卫', RB: '右卫', LB: '左卫', DM: '后腰',
    CM: '中场', AM: '前腰', RM: '右中', LM: '左中', RW: '右边', LW: '左边', ST: '前锋',
  }[pos] || pos || '-'
}

export function tendencyFromProbs(h, d, a) {
  const ranked = [
    ['home', h],
    ['draw', d],
    ['away', a],
  ].sort((x, y) => y[1] - x[1])
  const top = ranked[0]
  const margin = ranked[0][1] - ranked[1][1]
  if (top[0] === 'home') return margin > 0.12 ? '主队占优，主场加持明显' : '主队微优，需防平局'
  if (top[0] === 'away') return margin > 0.12 ? '客队占优，客场实力较强' : '客队微优，主队有主场抵抗'
  return '势均力敌，平局概率较高'
}

export function confidenceFromMax(maxProb) {
  if (maxProb > 0.5) return 'high'
  if (maxProb > 0.38) return 'mid'
  return 'low'
}

export function getScenarioEntry(scenarios, id) {
  if (!scenarios || !id) return null
  return scenarios[id] || scenarios[toCamelCase(id)] || null
}

export function normalizePrediction(raw) {
  const p = convertKeys(raw || {})
  if (typeof p.altScores === 'string') {
    try { p.altScores = JSON.parse(p.altScores) } catch { p.altScores = [] }
  }
  if (typeof p.keyVariables === 'string') {
    try { p.keyVariables = JSON.parse(p.keyVariables) } catch { p.keyVariables = [] }
  }
  if (typeof p.scoreMatrix === 'string') {
    try { p.scoreMatrix = JSON.parse(p.scoreMatrix) } catch { p.scoreMatrix = [] }
  }
  if (typeof p.weightsUsed === 'string') {
    try { p.weightsUsed = JSON.parse(p.weightsUsed) } catch { p.weightsUsed = null }
  }
  if (typeof p.metaJson === 'string') {
    try {
      const meta = JSON.parse(p.metaJson)
      Object.assign(p, convertKeys(meta || {}))
    } catch { /* ignore */ }
  } else if (p.metaJson && typeof p.metaJson === 'object') {
    Object.assign(p, convertKeys(p.metaJson))
  }
  p.homeWinProb = Number(p.homeWinProb ?? 0) || 0
  p.drawProb = Number(p.drawProb ?? 0) || 0
  p.awayWinProb = Number(p.awayWinProb ?? 0) || 0
  p.lambdaHome = Number(p.lambdaHome ?? 0) || 0
  p.lambdaAway = Number(p.lambdaAway ?? 0) || 0
  p.xgHome = p.xgHome != null && p.xgHome !== '' ? Number(p.xgHome) : null
  p.xgAway = p.xgAway != null && p.xgAway !== '' ? Number(p.xgAway) : null
  p.xgCoverage = p.xgCoverage != null && p.xgCoverage !== '' ? Number(p.xgCoverage) : null
  p.mainScore = p.mainScore || '-'
  p.totalGoals = p.totalGoals || '-'
  p.tendency = p.tendency || '暂无预测'
  p.confidence = p.confidence || 'mid'
  p.riskLevel = p.riskLevel || 'mid'
  p.analysis = p.analysis || ''
  p.modelVersion = p.modelVersion || ''
  p.altScores = Array.isArray(p.altScores) ? p.altScores : []
  p.keyVariables = Array.isArray(p.keyVariables) ? p.keyVariables : []
  p.scoreMatrix = Array.isArray(p.scoreMatrix) ? p.scoreMatrix : []
  if (p.scenarios && typeof p.scenarios === 'object' && !Array.isArray(p.scenarios)) {
    const mapped = {}
    for (const [k, v] of Object.entries(p.scenarios)) {
      const inner = convertKeys(v || {})
      const id = inner.id || k
      inner.id = id
      mapped[id] = inner
    }
    p.scenarios = mapped
  }
  p.scenarioOrder = Array.isArray(p.scenarioOrder) ? p.scenarioOrder : []
  p.primaryScenario = p.primaryScenario || ''
  p.scenarioReason = p.scenarioReason || ''
  p.scenarioLocked = !!p.scenarioLocked
  p.hasPrediction = !!(raw && (raw.home_win_prob != null || raw.homeWinProb != null))
  return p
}

export function normalizePlayerStats(rawList) {
  return (rawList || []).map((item) => {
    const p = convertKeys(item)
    p.goals = Number(p.goals || 0)
    p.assists = Number(p.assists || 0)
    p.shots = Number(p.shots || 0)
    p.shotsOnTarget = Number(p.shotsOnTarget || 0)
    p.passes = Number(p.passes || 0)
    p.tackles = Number(p.tackles || 0)
    p.yellowCards = Number(p.yellowCards || 0)
    p.minutesPlayed = Number(p.minutesPlayed || 0)
    p.rating = p.rating != null ? Number(p.rating) : null
    return p
  })
}

export function weightSourceTag(source) {
  if (!source) return 'tag-mid'
  if (String(source).startsWith('league:')) return 'tag-low'
  if (String(source).startsWith('scenario:')) return 'tag-info'
  if (source === 'global') return 'tag-info'
  return 'tag-mid'
}

export function xgCoverageText(cov) {
  if (cov == null || cov === '') return '未记录'
  const n = Number(cov)
  if (n >= 1) return '双方有样本'
  if (n >= 0.5) return '单方有样本'
  return '无样本（权重并入泊松）'
}

export function isAlertLocked(alert) {
  const locked = alert?.lockedFields || alert?.locked_fields || []
  return Array.isArray(locked) && locked.includes('description')
}
