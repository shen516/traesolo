import request from './http'

/** 积分榜接口 */
export const standingsApi = {
  getAll: () => request.get('/standings/'),
  getByLeague: (leagueId, season) => request.get(`/standings/league/${leagueId}`, { params: { season } }),
  create: (data) => request.post('/standings/', data),
  update: (id, data) => request.put(`/standings/${id}`, data),
  delete: (id) => request.delete(`/standings/${id}`)
}

/** 射手榜接口 */
export const scorersApi = {
  getAll: () => request.get('/scorers/'),
  getByLeague: (leagueId, season) => request.get(`/scorers/league/${leagueId}`, { params: { season } }),
  create: (data) => request.post('/scorers/', data),
  update: (id, data) => request.put(`/scorers/${id}`, data),
  delete: (id) => request.delete(`/scorers/${id}`)
}

/** 球员接口 */
export const playerApi = {
  getAll: () => request.get('/players/'),
  getById: (id) => request.get(`/players/${id}`),
  getByTeam: (teamId) => request.get('/players/', { params: { team_id: teamId } }),
  getByLeague: (leagueId) => request.get('/players/', { params: { league_id: leagueId } }),
  getByPosition: (position) => request.get('/players/', { params: { position } }),
  search: (keyword) => request.get('/players/', { params: { keyword } }),
  getTopScorers: (teamId = null, limit = 10) => request.get('/players/top-scorers', { params: { team_id: teamId, limit } }),
  create: (data) => request.post('/players', data),
  update: (id, data) => request.put(`/players/${id}`, data),
  delete: (id) => request.delete(`/players/${id}`)
}
