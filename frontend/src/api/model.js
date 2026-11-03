import request from './http'

/** 模型管理接口 */
export const modelApi = {
  getAll: () => request.get('/model/'),
  getStatus: () => request.get('/model/status'),
  getCurrent: () => request.get('/model/current'),
  getByVersion: (version) => request.get(`/model/${version}`),
  create: (data) => request.post('/model/', data),
  setCurrent: (id) => request.put(`/model/${id}/current`),
  delete: (id) => request.delete(`/model/${id}`),
  train: () => request.post('/model/train'),
  getTrainingStatus: () => request.get('/model/train/status'),
  getTrainingRecords: (params = {}) => request.get('/model/train/records', { params }),
  getTrainingRecord: (id) => request.get(`/model/train/records/${id}`),
  getLatestTrainingInsights: () => request.get('/model/train/insights/latest', { timeout: 60000 }),
  getMonitorCalibration: (params = {}) => request.get('/model/monitor/calibration', { params }),
  getMonitorDrift: (params = {}) => request.get('/model/monitor/drift', { params }),
  getMonitorOddsDeviation: (params = {}) => request.get('/model/monitor/odds-deviation', { params }),
  getJobStatus: (jobId) => request.get(`/model/jobs/${jobId}`),
}

/** 风控接口 */
export const riskApi = {
  getAll: (params = {}) => request.get('/risk/', { params }),
  getByMatch: (matchId) => request.get(`/risk/match/${matchId}`),
  getByLevel: (level, params = {}) => request.get(`/risk/level/${level}`, { params }),
  getUnprocessed: (params = {}) => request.get('/risk/unprocessed', { params }),
  create: (data) => request.post('/risk/', data),
  markProcessed: (id) => request.put(`/risk/${id}/process`, { is_processed: true }),
  setProcessed: (id, isProcessed) => request.put(`/risk/${id}/process`, { is_processed: !!isProcessed }),
  delete: (id) => request.delete(`/risk/${id}`)
}

/** 趋势接口 */
export const trendApi = {
  getAll: () => request.get('/trend/'),
  getByVersion: (version) => request.get(`/trend/version/${version}`),
  getRecent: (days = 30) => request.get(`/trend/recent/${days}`),
  create: (data) => request.post('/trend/', data),
  delete: (id) => request.delete(`/trend/${id}`)
}
