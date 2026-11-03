import request from './http'

/** 用户接口 */
export const userApi = {
  getAll: () => request.get('/users/'),
  getList: (params) => request.get('/users/', { params }),
  getAllSimple: () => request.get('/users/all'),
  getStats: () => request.get('/users/stats/summary'),
  getById: (id) => request.get(`/users/${id}`),
  register: (data) => request.post('/users/register', data),
  update: (id, data) => request.put(`/users/${id}`, data),
  resetPassword: (id, newPassword) => request.put(`/users/${id}/password`, { new_password: newPassword }),
  toggleStatus: (id, isActive) => request.put(`/users/${id}/status`, null, { params: { is_active: isActive } }),
  delete: (id) => request.delete(`/users/${id}`),
  getStatsById: (id) => request.get(`/users/${id}/stats`),
  setFavoriteTeam: (id, teamId) => request.put(`/users/${id}/favorite`, null, { params: { team_id: teamId } }),
  getPreferences: (id) => request.get(`/users/${id}/preferences`),
  updatePreferences: (id, data) => request.put(`/users/${id}/preferences`, data),
}

/** 订阅接口 */
export const subscriptionApi = {
  getPlans: () => request.get('/subscription/plans'),
  getMy: () => request.get('/subscription/my'),
  grant: (data) => request.post('/subscription/grant', data),
  cancel: (data) => request.post('/subscription/cancel', data),
  getRecords: (params = {}) => request.get('/subscription/records', { params }),
  runExpireCheck: () => request.post('/subscription/expire-check'),
}

/** 关注联赛接口 */
export const followApi = {
  list: (params = {}) => request.get('/follows/leagues', { params }),
  ids: (params = {}) => request.get('/follows/leagues/ids', { params }),
  follow: (leagueId) => request.post(`/follows/leagues/${leagueId}`),
  unfollow: (leagueId) => request.delete(`/follows/leagues/${leagueId}`),
  replace: (leagueIds, params = {}) => request.put('/follows/leagues', { league_ids: leagueIds }, { params }),
  summary: (params = {}) => request.get('/follows/summary', { params }),
}

/** 收藏接口 */
export const favoriteApi = {
  getByUser: (userId) => request.get(`/favorites/user/${userId}`),
  getUserMatches: (userId) => request.get(`/favorites/user/${userId}/matches`),
  getUserTeams: (userId) => request.get(`/favorites/user/${userId}/teams`),
  addMatch: (userId, matchId) => request.post(`/favorites/user/${userId}/match/${matchId}`),
  addTeam: (userId, teamId) => request.post(`/favorites/user/${userId}/team/${teamId}`),
  removeMatch: (userId, matchId) => request.delete(`/favorites/user/${userId}/match/${matchId}`),
  removeTeam: (userId, teamId) => request.delete(`/favorites/user/${userId}/team/${teamId}`)
}

/** 历史记录接口 */
export const historyApi = {
  getByUser: (userId, limit = 20) => request.get(`/history/user/${userId}`, { params: { limit } }),
  getAccuracy: (userId) => request.get(`/history/user/${userId}/accuracy`),
  create: (data) => request.post('/history', data),
  delete: (id) => request.delete(`/history/${id}`)
}
