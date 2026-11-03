import request from './http'

/** 赛事接口（竞彩相关见 jingcai.js） */
export const matchApi = {
  getAll: () => request.get('/matches/'),
  getById: (id) => request.get(`/matches/${id}`),
  getByDate: (date) => request.get(`/matches/date/${date}`),
  getByLeague: (leagueId) => request.get(`/matches/league/${leagueId}`),
  getUpcoming: (params = {}) => request.get('/matches/upcoming', { params: { page: 1, page_size: 20, ...params } }),
  getFinished: (params = {}) => request.get('/matches/finished', { params: { page: 1, page_size: 20, ...params } }),
  getByStatus: (status) => request.get(`/matches/status/${status}`),
  search: (keyword) => request.get(`/matches/search/${keyword}`),
  getPrediction: (matchId, recalculate = false) => request.get(`/matches/${matchId}/prediction`, { params: { recalculate } }),
  getPredictionHistory: (matchId, limit = 10) => request.get(`/matches/${matchId}/prediction/history`, { params: { limit } }),
  getPlayerStats: (matchId) => request.get(`/matches/${matchId}/player-stats`),
  getOddsSnapshots: (matchId, limit = 50) => request.get(`/matches/${matchId}/odds-snapshots`, { params: { limit } }),
  crawlHistorical: (leagueId = null, daysBack = 30, crawlType = 'manual') => request.post(`/matches/crawl/historical`, null, { params: { league_id: leagueId, days_back: daysBack, crawl_type: crawlType } }),
  create: (data) => request.post('/matches/', data),
  update: (id, data) => request.put(`/matches/${id}`, data),
  updateResult: (id, data) => request.put(`/matches/${id}/result`, data),
  delete: (id) => request.delete(`/matches/${id}`)
}
