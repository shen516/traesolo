/**
 * API 聚合出口：按域拆分后的模块统一从这里导出，
 * 既有 `import { matchApi } from '@/api'` 与 `import request from '@/api'` 的引用全部保持兼容。
 * 各域实现：
 *  - http.js       axios 实例与拦截器（默认导出 request）
 *  - auth.js       authApi
 *  - league.js     leagueApi
 *  - team.js       teamApi
 *  - match.js      matchApi（纯赛事域）
 *  - jingcai.js    jingcaiApi + matchJingcaiCompat（原 matchApi.getJingcai* 兼容层）
 *  - prediction.js predictionApi + modelStatusApi
 *  - user.js       userApi / subscriptionApi / followApi / favoriteApi / historyApi
 *  - model.js      modelApi / riskApi / trendApi
 *  - data.js       standingsApi / scorersApi / playerApi
 *  - schedule.js   scheduleApi
 *  - permission.js permissionApi
 */
import request from './http'
import { API_BASE_URL } from './http'
import { authApi } from './auth'
import { leagueApi } from './league'
import { teamApi } from './team'
import { matchApi } from './match'
import { jingcaiApi, matchJingcaiCompat } from './jingcai'
import { jingcaiTradeApi } from './jingcaiTrade'
import { predictionApi, modelStatusApi } from './prediction'
import { userApi, subscriptionApi, followApi, favoriteApi, historyApi } from './user'
import { modelApi, riskApi, trendApi } from './model'
import { standingsApi, scorersApi, playerApi } from './data'
import { scheduleApi } from './schedule'
import { permissionApi } from './permission'
import { simulationBetApi } from './simulationBet'

export {
  authApi,
  leagueApi,
  teamApi,
  matchApi,
  jingcaiApi,
  jingcaiTradeApi,
  predictionApi,
  modelStatusApi,
  userApi,
  subscriptionApi,
  followApi,
  favoriteApi,
  historyApi,
  modelApi,
  riskApi,
  trendApi,
  standingsApi,
  scorersApi,
  playerApi,
  scheduleApi,
  permissionApi,
  simulationBetApi,
  API_BASE_URL,
}

/**
 * 兼容别名：原三足鼎立的预测命名（predictionApi/predictApi/modelApi.status）
 * 统一为 predictionApi；旧 predictApi 引用转发（predict → compute）。
 */
export const predictApi = {
  predict: predictionApi.compute,
  status: modelStatusApi.status,
}

// matchApi 上保留 getJingcai* 方法名（指向 jingcaiApi 实现），旧页面无需改动
Object.assign(matchApi, matchJingcaiCompat)

export default request
