import request from './http'

/** 认证接口 */
export const authApi = {
  getCaptcha: () => request.get('/auth/captcha'),
  login: (data) => request.post('/auth/login', data),
  logout: () => request.post('/auth/logout'),
  /** 本人改密（强制改密流程走这里，成功返回 relogin_required） */
  changePassword: (data) => request.post('/auth/change-password', data)
}
