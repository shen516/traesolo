import request from './http'

/** 球队接口 */
export const teamApi = {
  getAll: () => request.get('/teams/'),
  getById: (id) => request.get(`/teams/${id}`),
  getByLeague: (leagueId) => request.get(`/teams/league/${leagueId}`),
  search: (keyword) => request.get(`/teams/search/${keyword}`),
  create: (data) => request.post('/teams/', data),
  update: (id, data) => request.put(`/teams/${id}`, data),
  updateElo: (id, elo) => request.put(`/teams/${id}/elo`, null, { params: { elo_rating: elo } }),
  updateStrength: (id, attack, defense) => request.put(`/teams/${id}/strength`, null, { params: { attack, defense } })
}
