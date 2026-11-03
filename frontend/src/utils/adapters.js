/** 后端 snake_case → 前端展示 DTO */

import { pickOddsFields, adaptOddsAnalysis } from '@/utils/matchMeta'

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

export function formatDateTime(dt) {
  if (!dt) return ''
  const date = new Date(dt)
  if (isNaN(date.getTime())) return ''
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${h}:${min}`
}

export function adaptTeam(t) {
  if (!t) return { id: '', name: '未知', short: '未知', logo: '⚪', elo: 1500, league: '' }
  return {
    id: t.id,
    name: t.name,
    short: t.short_name || t.short || t.name,
    logo: t.logo || '⚪',
    elo: t.elo_rating ?? t.elo ?? 1500,
    league: t.league_id ?? t.league ?? '',
  }
}

export function adaptLeague(l) {
  if (!l) return { id: '', name: '未知联赛', icon: '⚽', logo: '', category: 'domestic', country: '' }
  return {
    id: l.id,
    name: l.name,
    icon: l.icon || '⚽',
    logo: l.logo || '',
    category: l.category || 'domestic',
    country: l.country || '',
  }
}

const defaultUpcomingPrediction = {
  homeWinProb: 0,
  drawProb: 0,
  awayWinProb: 0,
  mainScore: '-',
  totalGoals: '-',
  tendency: '暂无预测',
  confidence: 'mid',
  riskLevel: 'mid',
  weightSource: null,
  xgCoverage: null,
  modelVersion: null,
  primaryScenario: null,
  scenarioLocked: false,
  hasPrediction: false,
}

/** 列表/详情通用的预测字段 */
export function adaptPrediction(p, { afterMatch = false, forFinished = false } = {}) {
  if (!p) {
    return forFinished
      ? {
          hasPrediction: false,
          afterMatch: false,
          mainScore: '-',
          tendency: '',
          homeWinProb: 0,
          drawProb: 0,
          awayWinProb: 0,
          outcome: null,
        }
      : { ...defaultUpcomingPrediction }
  }
  const mainScore = p.main_score || p.mainScore || '-'
  const homeWinProb = Number(p.home_win_prob ?? p.homeWinProb ?? 0)
  const drawProb = Number(p.draw_prob ?? p.drawProb ?? 0)
  const awayWinProb = Number(p.away_win_prob ?? p.awayWinProb ?? 0)
  const base = {
    homeWinProb,
    drawProb,
    awayWinProb,
    mainScore,
    totalGoals: p.total_goals || p.totalGoals || '-',
    tendency: p.tendency || (forFinished ? '' : '暂无预测'),
    confidence: p.confidence || 'mid',
    riskLevel: p.risk_level || p.riskLevel || 'mid',
    weightSource: p.weight_source || p.weightSource || null,
    xgCoverage: p.xg_coverage ?? p.xgCoverage ?? null,
    modelVersion: p.model_version || p.modelVersion || null,
    primaryScenario: p.primary_scenario || p.primaryScenario || null,
    scenarioLocked: !!(p.scenario_locked ?? p.scenarioLocked),
    hasPrediction: true,
  }
  if (forFinished) {
    return {
      ...base,
      afterMatch: !!afterMatch,
      outcome: predOutcomeFromPrediction(p, mainScore),
    }
  }
  return base
}

export function adaptUpcomingMatch(m) {
  const homeInfo = m.home_team ? adaptTeam(m.home_team) : null
  const awayInfo = m.away_team ? adaptTeam(m.away_team) : null
  const leagueInfo = m.league ? adaptLeague(m.league) : null
  return {
    id: m.id,
    league: m.league_id,
    homeTeam: m.home_team_id,
    awayTeam: m.away_team_id,
    homeTeamInfo: homeInfo,
    awayTeamInfo: awayInfo,
    leagueInfo,
    date: formatDate(m.match_date),
    time: formatTime(m.match_time),
    weather: m.weather || '',
    temperature: m.temperature || '',
    pitch: m.pitch_condition || '',
    venue: m.venue || '',
    status: m.status || 'upcoming',
    stage: m.stage || '',
    group: m.group_name || '',
    round: m.round_name || '',
    ...pickOddsFields(m),
    oddsAnalysis: adaptOddsAnalysis(m.odds_analysis || m.oddsAnalysis),
    prediction: adaptPrediction(m.prediction),
  }
}

function parseScore(text) {
  const m = String(text || '').match(/(\d+)\s*[-:]\s*(\d+)/)
  if (!m) return null
  return { home: Number(m[1]), away: Number(m[2]) }
}

export function actualOutcome(home, away) {
  if (home > away) return 'H'
  if (home < away) return 'A'
  return 'D'
}

function predOutcomeFromPrediction(raw, mainScore) {
  const parsed = parseScore(mainScore)
  if (parsed) return actualOutcome(parsed.home, parsed.away)
  const h = Number(raw.home_win_prob ?? raw.homeWinProb ?? 0)
  const d = Number(raw.draw_prob ?? raw.drawProb ?? 0)
  const a = Number(raw.away_win_prob ?? raw.awayWinProb ?? 0)
  const max = Math.max(h, d, a)
  if (h === max) return 'H'
  if (a === max) return 'A'
  return 'D'
}

export function adaptFinishedMatch(m) {
  const homeGoals = m.home_goals || 0
  const awayGoals = m.away_goals || 0
  const homeInfo = m.home_team ? adaptTeam(m.home_team) : null
  const awayInfo = m.away_team ? adaptTeam(m.away_team) : null
  const leagueInfo = m.league ? adaptLeague(m.league) : null
  return {
    id: m.id,
    league: m.league_id,
    homeTeam: m.home_team_id,
    awayTeam: m.away_team_id,
    homeTeamInfo: homeInfo,
    awayTeamInfo: awayInfo,
    leagueInfo,
    date: formatDate(m.match_date),
    time: formatTime(m.match_time),
    homeGoals,
    awayGoals,
    result: m.result || actualOutcome(homeGoals, awayGoals),
    venue: m.venue || '',
    weather: m.weather || '',
    temperature: m.temperature || '',
    totalGoals: homeGoals + awayGoals,
    stage: m.stage || '',
    group: m.group_name || '',
    round: m.round_name || '',
    ...pickOddsFields(m),
    oddsAnalysis: adaptOddsAnalysis(m.odds_analysis || m.oddsAnalysis),
    prediction: adaptPrediction(m.prediction, {
      afterMatch: !!m.prediction_after_match,
      forFinished: true,
    }),
  }
}

/** 首页精简赛事卡片 */
export function adaptDashboardMatch(raw) {
  const homeInfo = raw.home_team && typeof raw.home_team === 'object' ? adaptTeam(raw.home_team) : null
  const awayInfo = raw.away_team && typeof raw.away_team === 'object' ? adaptTeam(raw.away_team) : null
  const leagueInfo = raw.league && typeof raw.league === 'object' ? adaptLeague(raw.league) : null
  return {
    id: raw.id,
    league: raw.league_id || leagueInfo?.id || (typeof raw.league === 'string' ? raw.league : ''),
    homeTeam: raw.home_team_id || homeInfo?.id || (typeof raw.home_team === 'string' ? raw.home_team : ''),
    awayTeam: raw.away_team_id || awayInfo?.id || (typeof raw.away_team === 'string' ? raw.away_team : ''),
    homeTeamInfo: homeInfo,
    awayTeamInfo: awayInfo,
    leagueInfo,
    date: formatDate(raw.match_date ?? raw.date),
    time: formatTime(raw.match_time ?? raw.time),
    venue: raw.venue,
    status: raw.status,
    prediction: raw.prediction
      ? {
          tendency: raw.prediction.tendency || '暂无预测',
          mainScore: raw.prediction.main_score || raw.prediction.mainScore || '-',
          confidence: raw.prediction.confidence || 'mid',
          hasPrediction: true,
        }
      : {
          tendency: '暂无预测',
          mainScore: '-',
          confidence: 'mid',
          hasPrediction: false,
        },
  }
}

/** 从本页赛事嵌套字段构建球队 Map */
export function teamMapFromMatches(matches) {
  const map = new Map()
  for (const m of matches || []) {
    if (m.homeTeamInfo?.id) map.set(m.homeTeamInfo.id, m.homeTeamInfo)
    else if (m.homeTeam && m.homeTeamInfo) map.set(m.homeTeam, m.homeTeamInfo)
    if (m.awayTeamInfo?.id) map.set(m.awayTeamInfo.id, m.awayTeamInfo)
    else if (m.awayTeam && m.awayTeamInfo) map.set(m.awayTeam, m.awayTeamInfo)
  }
  return map
}

export function adaptStandings(raw) {
  return {
    rank: raw.rank ?? raw.position,
    team: raw.team_id ?? raw.team,
    played: raw.played ?? raw.matches_played,
    won: raw.won ?? raw.wins,
    drawn: raw.drawn ?? raw.draws,
    lost: raw.lost ?? raw.losses,
    gf: raw.goals_for ?? raw.gf,
    ga: raw.goals_against ?? raw.ga,
    points: raw.points,
  }
}

export function adaptScorer(raw) {
  return {
    rank: raw.rank ?? raw.position,
    name: raw.player_name ?? raw.name,
    team: raw.team_id ?? raw.team,
    goals: raw.goals || 0,
    assists: raw.assists || 0,
  }
}

export function adaptRisk(raw) {
  return {
    id: raw.id,
    matchId: raw.match_id,
    match: raw.match ?? raw.match_name ?? '未知赛事',
    type: raw.type ?? raw.risk_type ?? '风险',
    level: raw.level ?? raw.risk_level ?? 'mid',
    description: raw.description || '',
    time: raw.time ?? raw.created_at ?? '',
    leagueId: raw.league_id || raw.leagueId || '',
  }
}

export function adaptTrend(raw) {
  return {
    date: raw.date,
    accuracy: raw.accuracy ?? raw.accuracy_rate,
  }
}

export function unwrapList(res, key) {
  if (Array.isArray(res)) return res
  if (res && Array.isArray(res[key])) return res[key]
  return []
}

export function isExactScoreHit(match) {
  if (!match.prediction?.hasPrediction) return false
  const parsed = parseScore(match.prediction.mainScore)
  if (!parsed) return false
  return parsed.home === match.homeGoals && parsed.away === match.awayGoals
}

export function isOutcomeHit(match) {
  if (!match.prediction?.hasPrediction) return false
  return match.prediction.outcome === actualOutcome(match.homeGoals, match.awayGoals)
}

export function hitText(match) {
  if (isExactScoreHit(match)) return '比分命中'
  if (isOutcomeHit(match)) return '赛果命中'
  return '未命中'
}

export function hitTagClass(match) {
  if (isExactScoreHit(match)) return 'tag-low'
  if (isOutcomeHit(match)) return 'tag-info'
  return 'tag-high'
}
