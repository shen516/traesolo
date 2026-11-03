import request from './http'

/**
 * 竞彩足球接口（比分投注区 / 历史比分 / 月度汇总 / 配置 / 相似盘口推荐）。
 * 由原 matchApi 混域部分迁出。
 */
export const jingcaiApi = {
  getBf: (params = {}) => request.get('/matches/jingcai/bf', { params: { page: 1, page_size: 50, view: 'summary', ...params } }),
  refreshBf: (params = {}) => request.post('/matches/jingcai/bf/refresh', null, { params, timeout: 180000 }),
  // 竞彩比分列表（live.500.com/jczq.php）
  getLive: (params = {}) => request.get('/matches/jingcai/live', { params: { page: 1, page_size: 50, view: 'summary', ...params } }),
  refreshLive: (params = {}) => request.post('/matches/jingcai/live/refresh', null, { params, timeout: 180000 }),
  getBfHistory: (params = {}) => request.get('/matches/jingcai/bf/expired', { params: { page: 1, page_size: 50, view: 'summary', ...params } }),
  getBfSummary: (params = {}) => request.get('/matches/jingcai/bf/monthly-summary', { params }),
  getConfig: () => request.get('/matches/jingcai/config'),
  updateConfig: (recommendScoreCount) => request.put('/matches/jingcai/config', { recommend_score_count: recommendScoreCount }),
  refreshExpiredScores: (params = {}) => request.post('/matches/jingcai/expired/refresh-scores', null, { params, timeout: 180000 }),
  // 历史相似盘口比分推荐：nspf / spf 取 any | auto | H | D | A；个数由竞彩配置决定
  getScoreTop3: (matchIds, params = {}) => request.get('/matches/jingcai/score-top3', { params: { match_ids: [].concat(matchIds).join(','), ...params } }),
  getScoreTop3Backtest: (days = 60) => request.get('/matches/jingcai/score-top3/backtest', { params: { days }, timeout: 120000 }),
}

/** 兼容旧引用：原 matchApi.getJingcai* 方法名 */
export const matchJingcaiCompat = {
  getJingcaiBf: jingcaiApi.getBf,
  refreshJingcaiBf: jingcaiApi.refreshBf,
  getJingcaiBfHistory: jingcaiApi.getBfHistory,
  getJingcaiBfSummary: jingcaiApi.getBfSummary,
  getJingcaiConfig: jingcaiApi.getConfig,
  updateJingcaiConfig: jingcaiApi.updateConfig,
  refreshJingcaiExpiredScores: jingcaiApi.refreshExpiredScores,
  getJingcaiScoreTop3: jingcaiApi.getScoreTop3,
  getJingcaiScoreTop3Backtest: jingcaiApi.getScoreTop3Backtest,
}
