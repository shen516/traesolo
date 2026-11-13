import request from './http'

/** 模拟投注单接口（仅供学习/研究，不接入真实资金） */
export const simulationBetApi = {
  list: (params = {}) => request.get('/simulation/bets', { params }),
  create: (data) => request.post('/simulation/bets', data),
  createParlay: (data) => request.post('/simulation/bets/parlay', data),
  detail: (id) => request.get(`/simulation/bets/${id}`),
  voidBet: (id) => request.post(`/simulation/bets/${id}/void`),
  stats: () => request.get('/simulation/bets/stats'),
  settleAll: () => request.post('/simulation/bets/settle-all'),
}
