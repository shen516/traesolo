import request from './http'

/**
 * 预测接口：持久化预测记录 + 批量计算/重算。
 * （直接双队计算的 /predict 端点也已并入本组 compute）
 */
export const predictionApi = {
  getAll: () => request.get('/predictions/'),
  getByMatch: (matchId) => request.get(`/predictions/match/${matchId}`),
  create: (data) => request.post('/predictions/', data),
  update: (matchId, data) => request.put(`/predictions/match/${matchId}`, data),
  calculate: (homeTeam, awayTeam, matchId = null) => request.post('/predictions/calculate', { home_team: homeTeam, away_team: awayTeam, match_id: matchId }),
  batchCalculate: (matchIds, recalculate = false) => request.post('/predictions/batch', { match_ids: matchIds, recalculate }, { timeout: 120000 }),
  /** 按新模型批量重算：scope=upcoming|ids；only_stale 默认只补过期/缺 meta */
  recalculate: (payload = {}) => request.post('/predictions/recalculate', {
    scope: 'upcoming',
    only_stale: true,
    include_unpredicted: true,
    limit: 150,
    ...payload,
  }, { timeout: 300000 }),
  staleStats: (params = {}) => request.get('/predictions/stale-stats', { params }),
  /** 切换/锁定主结论场景（不重跑模型） */
  setScenario: (matchId, scenarioId, lock = true) =>
    request.post(`/predictions/match/${matchId}/scenario`, {
      scenario_id: scenarioId,
      lock: !!lock,
    }),
  delete: (id) => request.delete(`/predictions/${id}`),
  /** 直接双队计算（原独立 predictApi.predict） */
  compute: (homeTeam, awayTeam) => request.post('/predict', { home_team: homeTeam, away_team: awayTeam }),
}

/** 模型状态（原独立 predictApi.status，供监控页使用） */
export const modelStatusApi = {
  status: () => request.get('/model/status')
}
