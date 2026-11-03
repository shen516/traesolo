import { defineStore } from 'pinia'
import { authApi, userApi, subscriptionApi } from '@/api'
import { useFollowsStore } from '@/stores/follows'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    roles: JSON.parse(localStorage.getItem('roles') || '[]'),
    permissions: JSON.parse(localStorage.getItem('permissions') || '[]'),
    features: JSON.parse(localStorage.getItem('features') || '[]'),
    // 首次登录必须改密（出厂弱口令账号）。持久化：页面刷新后仍要拦截。
    mustChangePassword: localStorage.getItem('must_change_password') === '1',
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
    username: (state) => state.user?.username || '',
    level: (state) => state.user?.level || 'free',
    isAdmin: (state) => (state.roles || []).some(r => ['admin', 'super_admin'].includes(r.code)),
    // 订阅权益判断：admin 角色视为全量权益
    hasFeature: (state) => (code) => {
      if ((state.roles || []).some(r => ['admin', 'super_admin'].includes(r.code))) return true
      return (state.features || []).includes(code)
    },
  },

  actions: {
    clearSession() {
      this.token = ''
      this.user = null
      this.roles = []
      this.permissions = []
      this.features = []
      this.mustChangePassword = false
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      localStorage.removeItem('roles')
      localStorage.removeItem('permissions')
      localStorage.removeItem('features')
      localStorage.removeItem('must_change_password')
      try {
        useFollowsStore().clear()
      } catch (_) {
        /* Pinia 未就绪时忽略 */
      }
    },

    async login(loginData) {
      const res = await authApi.login(loginData)
      this.token = res.token
      this.user = res.user
      this.roles = res.roles || []
      this.permissions = res.permissions || []
      this.features = res.features || []
      // 后端在 user 里返回 must_change_password；仅作软提示，不再路由拦截
      this.mustChangePassword = !!(res.user && res.user.must_change_password)
      localStorage.setItem('token', res.token)
      localStorage.setItem('user', JSON.stringify(res.user))
      localStorage.setItem('roles', JSON.stringify(this.roles))
      localStorage.setItem('permissions', JSON.stringify(this.permissions))
      localStorage.setItem('features', JSON.stringify(this.features))
      localStorage.setItem('must_change_password', this.mustChangePassword ? '1' : '0')
      try {
        await useFollowsStore().hydrateFromPreferences(this.user?.id)
      } catch (_) {
        /* 关注列表失败不阻断登录 */
      }
      return res
    },

    /**
     * 本人改密（强制改密走这里）。
     * 后端成功会吊销当前 token 并要求重新登录，所以成功后自动清会话跳登录页。
     * 校验旧密码时后端可能返回 403（账号已禁用）或 429（限流），
     * 直接抛出文案让表单展示，不触发"登录过期"跳转。
     */
    async changePassword({ oldPassword, newPassword }) {
      const res = await authApi.changePassword({
        old_password: oldPassword,
        new_password: newPassword,
      })
      // 后端返回 200 时会吊销 token；前端必须清掉本地会话
      this.mustChangePassword = false
      localStorage.removeItem('must_change_password')
      this.clearSession()
      return res
    },

    async logout() {
      try {
        await authApi.logout()
      } catch (_) {
        // 忽略退出登录错误
      }
      this.clearSession()
    },

    async fetchUserInfo(userId) {
      const res = await userApi.getById(userId)
      this.user = res
      localStorage.setItem('user', JSON.stringify(res))
      return res
    },

    // 订阅变更后（管理员开通/取消、到期翻转）刷新权益码与订阅快照
    async refreshSubscription() {
      try {
        const sub = await subscriptionApi.getMy()
        this.features = sub.features || []
        localStorage.setItem('features', JSON.stringify(this.features))
        if (this.user) {
          this.user = {
            ...this.user,
            subscription_plan: sub.plan_code,
            subscription_status: sub.status,
            subscription_expire: sub.expire_date,
          }
          localStorage.setItem('user', JSON.stringify(this.user))
        }
        return sub
      } catch (e) {
        console.warn('刷新订阅权益失败:', e)
        return null
      }
    },
  }
})
