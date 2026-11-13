import request from './http'

/**
 * 竞彩足球全玩法接口（trade.500.com/jczq 列表：单关/胜平负/让球/混合过关/比分/进球数/半全场）。
 * 只读列表展示，无投注功能。后端路由前缀 /api/v1/jingcai/trade。
 */
export const jingcaiTradeApi = {
  // 按玩法查询在售比赛列表
  // play: dg | spf | nspf | hhgg | bf | jqs | bqc
  getMatches: (params = {}) => request.get('/jingcai/trade/matches', { params }),
  // 有数据的销售日列表（倒序）
  getDates: (params = {}) => request.get('/jingcai/trade/dates', { params }),
  // 支持的过关方式（单关 + M串N）
  getPassTypes: () => request.get('/jingcai/trade/pass-types'),
  // 选号奖金计算（只读计算，不产生投注）
  calculate: (data) => request.post('/jingcai/trade/calculate', data),
  // 触发全玩法采集（仅管理员/采集权限）
  refresh: (params = {}) => request.post('/jingcai/trade/refresh', null, { params, timeout: 180000 }),
  // 历史数据回补（近 days_back 个销售日 SP+赛果，仅管理权限）
  history: (params = {}) => request.post('/jingcai/trade/history', null, { params, timeout: 600000 }),
  // 赛果校验（只读对照，仅管理权限）
  verify: (params = {}) => request.post('/jingcai/trade/verify', null, { params, timeout: 600000 }),
  // 最近 SP 异动记录（仅供分析）
  getSpChanges: (params = {}) => request.get('/jingcai/trade/sp-changes', { params }),
  // 数据导出（CSV 下载）
  exportCsv: (params = {}) => request.get('/jingcai/trade/export', { params, responseType: 'blob' }),
  // 汇总统计报表
  getSummary: (params = {}) => request.get('/jingcai/trade/summary', { params }),
}
