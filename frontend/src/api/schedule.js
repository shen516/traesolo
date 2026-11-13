import axios from 'axios'
import request, { API_BASE_URL } from './http'

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** 手动采集接口只返回 job_id；页面仍等待结束后再刷新数据。 */
async function pollCrawlerJob(queued, timeoutMs = 180000) {
  if (!queued?.job_id || queued.async !== true) return queued
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    const st = await request.get(`/crawler/jobs/${queued.job_id}`, { timeout: 15000 })
    const status = st?.status
    if (status === 'finished') {
      let payload = st.result
      if (
        payload &&
        typeof payload === 'object' &&
        !Array.isArray(payload) &&
        payload.ok === true &&
        Object.prototype.hasOwnProperty.call(payload, 'result')
      ) {
        payload = payload.result
      }
      if (Array.isArray(payload)) {
        return { message: '采集完成', job_id: queued.job_id, result: payload, results: payload }
      }
      if (payload && typeof payload === 'object') {
        return { ...payload, message: payload.message || '采集完成', job_id: queued.job_id }
      }
      return { message: '采集完成', job_id: queued.job_id, result: payload }
    }
    if (status === 'failed' || status === 'stopped' || status === 'canceled') {
      const raw = typeof st?.exc_info === 'string' ? st.exc_info.trim() : ''
      const line = raw ? raw.split('\n').filter(Boolean).pop() : '采集失败'
      throw new Error(line || '采集失败')
    }
    await sleep(2000)
  }
  throw new Error('采集仍在后台执行，请稍后查看采集日志')
}

async function postCrawlAndWait(url, config = {}, timeoutMs = 180000) {
  const queued = await request.post(url, null, { ...config, timeout: 30000 })
  return pollCrawlerJob(queued, timeoutMs)
}

/** 定时任务管理 */
export const scheduleApi = {
  // 调度器状态
  getStatus: () => request.get('/crawler/status'),

  // 赛事采集任务
  enableMatch: (interval = 60) => request.post('/crawler/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableMatch: () => request.post('/crawler/schedule/disable'),
  runMatchNow: () => request.post('/crawler/schedule/run-now'),

  // Live500采集任务
  enableLive500: (interval = 30) => request.post('/crawler/live500/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableLive500: () => request.post('/crawler/live500/schedule/disable'),
  runLive500Now: () => request.post('/crawler/live500/schedule/run-now'),

  // 胜平负/让球（竞彩赔率，分析用）
  enableJingcaiOdds: (interval = 30) => request.post('/crawler/jingcai-odds/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableJingcaiOdds: () => request.post('/crawler/jingcai-odds/schedule/disable'),
  runJingcaiOddsNow: () => request.post('/crawler/jingcai-odds/schedule/run-now', null, { timeout: 180000 }),
  runJingcaiOdds: (daysAhead = 7) => postCrawlAndWait('/crawler/jingcai-odds/run', { params: { days_ahead: daysAhead } }, 180000),
  // 竞彩比分投注区
  enableJingcaiBf: (interval = 30) => request.post('/crawler/jingcai-bf/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableJingcaiBf: () => request.post('/crawler/jingcai-bf/schedule/disable'),
  runJingcaiBfNow: () => request.post('/crawler/jingcai-bf/schedule/run-now', null, { timeout: 180000 }),
  runJingcaiBf: (daysAhead = 7) => postCrawlAndWait('/crawler/jingcai-bf/run', { params: { days_ahead: daysAhead } }, 180000),
  // 竞彩分析历史比分回补（playid=271 历史日期）
  enableJingcaiBfHistory: (interval = 360) => request.post('/crawler/jingcai-bf-history/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableJingcaiBfHistory: () => request.post('/crawler/jingcai-bf-history/schedule/disable'),
  runJingcaiBfHistoryNow: () => request.post('/crawler/jingcai-bf-history/schedule/run-now', null, { timeout: 600000 }),
  runJingcaiBfHistory: (daysBack = 30) => postCrawlAndWait('/crawler/jingcai-bf-history/run', { params: { days_back: daysBack } }, 600000),
  // 竞彩赛果回写（胜平负 date 回查）
  enableJingcaiScores: (interval = 60) => request.post('/crawler/jingcai-scores/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableJingcaiScores: () => request.post('/crawler/jingcai-scores/schedule/disable'),
  runJingcaiScoresNow: () => request.post('/crawler/jingcai-scores/schedule/run-now', null, { timeout: 180000 }),
  runJingcaiScores: (daysBack = 7) => postCrawlAndWait('/crawler/jingcai-scores/run', { params: { days_back: daysBack } }, 180000),
  // 竞彩比分列表（live.500.com/jczq.php）
  enableLiveJingcai: (interval = 30) => request.post('/crawler/live-jingcai/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableLiveJingcai: () => request.post('/crawler/live-jingcai/schedule/disable'),
  runLiveJingcaiNow: () => request.post('/crawler/live-jingcai/schedule/run-now', null, { timeout: 180000 }),
  runLiveJingcai: (daysAhead = 1) => postCrawlAndWait('/crawler/live-jingcai/run', { params: { days_ahead: daysAhead } }, 180000),

  // 竞彩全玩法（trade.500.com 混合过关 + 进球数）
  enableJingcaiTrade: (interval = 30) => request.post('/crawler/jingcai-trade/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableJingcaiTrade: () => request.post('/crawler/jingcai-trade/schedule/disable'),
  runJingcaiTradeNow: () => request.post('/crawler/jingcai-trade/schedule/run-now', null, { timeout: 300000 }),
  runJingcaiTrade: (daysAhead = 7) => postCrawlAndWait('/crawler/jingcai-trade/run', { params: { days_ahead: daysAhead } }, 300000),
  // 竞彩全玩法轮询（临近开赛/待回补赛果时轻量抓取）
  enableJingcaiTradePoll: (interval = 5) => request.post('/crawler/jingcai-trade-poll/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableJingcaiTradePoll: () => request.post('/crawler/jingcai-trade-poll/schedule/disable'),
  runJingcaiTradePollNow: () => request.post('/crawler/jingcai-trade-poll/schedule/run-now', null, { timeout: 180000 }),
  // 竞彩全玩法历史回补（赛果对照）
  enableJingcaiTradeHistory: (interval = 360) => request.post('/crawler/jingcai-trade-history/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableJingcaiTradeHistory: () => request.post('/crawler/jingcai-trade-history/schedule/disable'),
  runJingcaiTradeHistoryNow: (daysBack = 30) => request.post('/crawler/jingcai-trade-history/schedule/run-now', null, { params: { days_back: daysBack }, timeout: 600000 }),

  // 伤病采集（分析风控）
  enableInjuryCrawl: (interval = 120) => request.post('/crawler/injuries/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableInjuryCrawl: () => request.post('/crawler/injuries/schedule/disable'),
  runInjuryCrawlNow: () => request.post('/crawler/injuries/schedule/run-now', null, { timeout: 300000 }),
  runInjuryCrawl: () => postCrawlAndWait('/crawler/injuries/run', {}, 300000),

  // 联赛采集任务
  enableLeague: (interval = 1440) => request.post('/crawler/leagues/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableLeague: () => request.post('/crawler/leagues/schedule/disable'),
  runLeagueNow: () => request.post('/crawler/leagues/schedule/run-now'),

  enableTeam: (interval = 1440) => request.post('/crawler/teams/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableTeam: () => request.post('/crawler/teams/schedule/disable'),
  runTeamNow: () => request.post('/crawler/teams/schedule/run-now'),
  enableSquad: (interval = 1440) => request.post('/crawler/players/squad/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableSquad: () => request.post('/crawler/players/squad/schedule/disable'),
  runSquadNow: () => request.post('/crawler/players/squad/schedule/run-now', null, { timeout: 600000 }),
  runTeamCrawl: (leagueId = null, include500 = false) => postCrawlAndWait('/crawler/teams/run', { params: { league_id: leagueId, include_500: include500 } }, 180000),
  enrichLeague: (leagueId, includeHistory = false, seasonsBack = 0) => postCrawlAndWait('/crawler/leagues/enrich', { params: { league_id: leagueId, include_history: includeHistory, seasons_back: seasonsBack } }, 300000),
  enrichAllLeagues: (includeHistory = true, seasonsBack = 2) => request.post('/crawler/leagues/enrich-all', null, { params: { include_history: includeHistory, seasons_back: seasonsBack }, timeout: 900000 }),
  crawlStandings: (leagueId = null) => postCrawlAndWait('/crawler/standings/run', { params: { league_id: leagueId } }, 180000),
  crawlScorers: (leagueId = null) => postCrawlAndWait('/crawler/scorers/run', { params: { league_id: leagueId } }, 300000),
  enableStandingsSchedule: (interval = 360) => request.post('/crawler/standings/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableStandingsSchedule: () => request.post('/crawler/standings/schedule/disable'),
  runStandingsScheduleNow: () => request.post('/crawler/standings/schedule/run-now', null, { timeout: 180000 }),
  enableScorersSchedule: (interval = 360) => request.post('/crawler/scorers/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableScorersSchedule: () => request.post('/crawler/scorers/schedule/disable'),
  runScorersScheduleNow: () => request.post('/crawler/scorers/schedule/run-now', null, { timeout: 300000 }),
  crawlImages: (leagueId = null, includePlayers = true) => postCrawlAndWait('/crawler/images/run', { params: { league_id: leagueId, include_players: includePlayers } }, 600000),

  // 手动采集
  runMatchCrawl: (leagueId = null) => postCrawlAndWait('/crawler/run', { params: { league_id: leagueId } }, 180000),
  runPlayerCrawl: (leagueId = null, teamId = null) => postCrawlAndWait('/crawler/players/run', { params: { league_id: leagueId, team_id: teamId } }, 180000),

  // 球员进球统计任务
  enablePlayerStats: (interval = 360) => request.post('/crawler/players/stats/schedule/enable', null, { params: { interval_minutes: interval } }),
  disablePlayerStats: () => request.post('/crawler/players/stats/schedule/disable'),
  runPlayerStatsNow: () => request.post('/crawler/players/stats/schedule/run-now'),
  runPlayerStatsCrawl: (leagueId = null, teamId = null) => postCrawlAndWait('/crawler/players/stats/run', { params: { league_id: leagueId, team_id: teamId } }, 180000),

  // 逐场球员统计任务
  enableMatchPlayerStats: (interval = 360) => request.post('/crawler/matches/player-stats/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableMatchPlayerStats: () => request.post('/crawler/matches/player-stats/schedule/disable'),
  runMatchPlayerStatsNow: () => request.post('/crawler/matches/player-stats/schedule/run-now'),
  runMatchPlayerStatsCrawl: (matchId = null, leagueId = null, limit = 50) =>
    postCrawlAndWait('/crawler/matches/player-stats/run', {
      params: { match_id: matchId, league_id: leagueId, limit, prioritize_mappable: true },
    }, 600000),
  backfillMatchPlayerStats: (limitPerLeague = 250, preferOlder = true) =>
    request.post('/crawler/matches/player-stats/backfill', null, {
      params: { limit_per_league: limitPerLeague, prefer_older: preferOlder },
      timeout: 3600000,
    }),
  runP0Pipeline: (params = {}) => request.post('/crawler/p0/run', null, {
    params: {
      stats_limit_per_league: 500,
      env_limit: 1000,
      train: true,
      enable_environment_schedule: true,
      ...params,
    },
    timeout: 30000,
  }),
  getP0Status: () => request.get('/crawler/p0/status', { timeout: 15000 }),
  getJobStatus: (jobId) => request.get(`/crawler/jobs/${jobId}`, { timeout: 15000 }),
  runUelCatchup: (params = {}) => request.post('/crawler/uel/catchup', null, {
    params: {
      include_history: true,
      seasons_back: 2,
      stats_limit: 250,
      train: true,
      use_queue: true,
      ...params,
    },
    timeout: 30000,
  }),
  runExtendedCatchup: (params = {}) => request.post('/crawler/extended/catchup', null, {
    params: {
      include_history: true,
      seasons_back: 1,
      stats_limit: 80,
      train: false,
      include_p3: true,
      use_queue: true,
      ...params,
    },
    timeout: 30000,
  }),

  enableImage: (interval = 720) => request.post('/crawler/images/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableImage: () => request.post('/crawler/images/schedule/disable'),
  runImageNow: () => request.post('/crawler/images/schedule/run-now'),

  // 重点联赛赛果增量 + 自动训练
  enablePriorityTrain: (interval = 720) => request.post('/crawler/priority-train/schedule/enable', null, { params: { interval_minutes: interval } }),
  disablePriorityTrain: () => request.post('/crawler/priority-train/schedule/disable'),
  runPriorityTrainNow: () => request.post('/crawler/priority-train/schedule/run-now'),

  // 气象环境补全（Open-Meteo）
  backfillEnvironment: (params = {}) => postCrawlAndWait('/crawler/environment/backfill', {
    params: { limit: 1000, only_missing: true, ...params },
  }, 300000),
  enableEnvironmentSchedule: (interval = 360) => request.post('/crawler/environment/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableEnvironmentSchedule: () => request.post('/crawler/environment/schedule/disable'),
  runEnvironmentScheduleNow: () => request.post('/crawler/environment/schedule/run-now', null, { timeout: 300000 }),

  enableQualityAlertsSchedule: (interval = 360) => request.post('/crawler/quality-alerts/schedule/enable', null, { params: { interval_minutes: interval } }),
  disableQualityAlertsSchedule: () => request.post('/crawler/quality-alerts/schedule/disable'),
  runQualityAlertsScheduleNow: () => request.post('/crawler/quality-alerts/schedule/run-now', null, { timeout: 120000 }),
  runQualityAlerts: () => postCrawlAndWait('/crawler/quality-alerts/run', {}, 180000),

  // 数据质量看板（覆盖率 / 训练滞后 / 映射缺口）
  getDataQuality: () => request.get('/crawler/data-quality', { timeout: 60000 }),
  getDataQualitySummary: () => request.get('/crawler/data-quality/summary', { timeout: 30000 }),
  getDataQualityByLeague: (params = {}) => request.get('/crawler/data-quality/by-league', {
    params: { page: 1, page_size: 50, ...params },
    timeout: 30000,
  }),
  getMappingGaps: (limitPerLeague = 40) => request.get('/crawler/mapping-gaps', {
    params: { limit_per_league: limitPerLeague },
    timeout: 90000,
  }),
  getMappingGapsSummary: () => request.get('/crawler/mapping-gaps/summary', { timeout: 60000 }),
  getMappingGapsRows: (params = {}) => request.get('/crawler/mapping-gaps/rows', {
    params: { page: 1, page_size: 20, ...params },
    timeout: 60000,
  }),
  listTeamAliases: (params = {}) => request.get('/crawler/team-aliases', { params, timeout: 30000 }),
  createTeamAlias: (data) => request.post('/crawler/team-aliases', data),
  updateTeamAlias: (id, data) => request.put(`/crawler/team-aliases/${id}`, data),
  deleteTeamAlias: (id) => request.delete(`/crawler/team-aliases/${id}`),
  suggestTeamAliases: () => request.post('/crawler/team-aliases/suggest', null, { timeout: 60000 }),

  // 采集日志
  getLogs: (params) => request.get('/crawler/logs', { params }),
  getLogStats: (hours = 24) => request.get('/crawler/logs/stats', { params: { hours } }),
  getLogById: (id) => request.get(`/crawler/logs/${id}`),
  deleteLog: (id) => request.delete(`/crawler/logs/${id}`),
  cleanOldLogs: (days = 30) => request.delete('/crawler/logs/clean', { params: { days } }),

  // 系统运行日志（启动后控制台同级输出）
  getRuntimeLogs: () => request.get('/crawler/runtime-logs'),
  getRuntimeLogTail: (params = {}) => request.get('/crawler/runtime-logs/tail', { params }),
  downloadRuntimeLog: async (name = null) => {
    const token = localStorage.getItem('token')
    const res = await axios.get(`${API_BASE_URL}/crawler/runtime-logs/download`, {
      params: name ? { name } : {},
      responseType: 'blob',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    return res.data
  },

  // 联赛字典
  getLeagues: () => request.get('/crawler/leagues')
}
