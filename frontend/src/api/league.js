import request from './http'

/**
 * 联赛接口。
 * 集合根路径必须带尾斜杠：FastAPI 对 /leagues → /leagues/ 会 307，
 * 经 Vite 代理时 Location 变成后端绝对地址，浏览器跟随后丢掉 Authorization → 401 被踢回登录页
 */
export const leagueApi = {
  getAll: (params = {}) => request.get('/leagues/', { params: { page_size: 500, hide_duplicates: true, ...params } }),
  getList: (params = {}) => request.get('/leagues/', { params: { page_size: 500, hide_duplicates: true, ...params } }),
  getActive: () => request.get('/leagues/active'),
  getById: (id) => request.get(`/leagues/${id}`),
  getChildren: (id, params = {}) => request.get(`/leagues/${id}/children`, { params }),
  getRoots: () => request.get('/leagues/roots'),
  backfillParents: () => request.post('/leagues/backfill-parents'),
  getCategories: () => request.get('/leagues/categories'),
  getCountries: (category = null) => request.get('/leagues/countries', { params: { category } }),
  create: (data) => request.post('/leagues/', data),
  update: (id, data) => request.put(`/leagues/${id}`, data),
  toggleActive: (id) => request.put(`/leagues/${id}/toggle`),
  delete: (id) => request.delete(`/leagues/${id}`)
}
