import { defineStore } from 'pinia'
import { followApi, userApi } from '@/api'

const STORAGE_KEY = 'followIncludeChildren'

function readIncludeChildren() {
  return localStorage.getItem(STORAGE_KEY) === '1'
}

export const useFollowsStore = defineStore('follows', {
  state: () => ({
    ids: [],
    filterIds: [],
    childMap: {},
    leagues: [],
    includeChildren: readIncludeChildren(),
    loaded: false,
    loading: false,
  }),

  getters: {
    isFollowed: (state) => (leagueId) => state.ids.includes(leagueId),
    count: (state) => state.ids.length,
    queryIds: (state) => (state.filterIds.length ? state.filterIds : state.ids),
    queryIdSet() {
      return new Set(this.queryIds)
    },
  },

  actions: {
    applyPayload(res) {
      if (!res) return
      this.leagues = res.leagues || this.leagues
      this.ids = res.ids || (this.leagues || []).map((l) => l.id)
      this.filterIds = res.filter_ids || this.ids
      this.childMap = res.child_map || {}
      this.loaded = true
    },

    persistIncludeChildren(value) {
      this.includeChildren = !!value
      localStorage.setItem(STORAGE_KEY, this.includeChildren ? '1' : '0')
    },

    clear() {
      this.ids = []
      this.filterIds = []
      this.childMap = {}
      this.leagues = []
      this.loaded = false
      this.loading = false
    },

    async fetch() {
      this.loading = true
      try {
        const res = await followApi.list({ include_children: this.includeChildren })
        this.applyPayload(res)
        return this.leagues
      } catch (e) {
        console.warn('加载关注联赛失败:', e)
        return this.leagues
      } finally {
        this.loading = false
        this.loaded = true
      }
    },

    async ensureLoaded() {
      if (this.loaded) return this.leagues
      if (this.loading) return this.leagues
      return this.fetch()
    },

    async setIncludeChildren(value) {
      const next = !!value
      if (this.includeChildren === next && this.loaded) return this.leagues
      this.persistIncludeChildren(next)
      this.loaded = false
      return this.fetch()
    },

    async hydrateFromPreferences(userId) {
      if (userId) {
        try {
          const pref = await userApi.getPreferences(userId)
          if (pref && pref.follow_include_children != null) {
            const next = !!pref.follow_include_children
            if (this.includeChildren !== next) {
              this.persistIncludeChildren(next)
              this.loaded = false
            }
          }
        } catch (_) {
          /* 偏好读取失败时沿用本地开关 */
        }
      }
      return this.ensureLoaded()
    },

    async replace(leagueIds) {
      const res = await followApi.replace(leagueIds, { include_children: this.includeChildren })
      this.applyPayload(res)
      return this.leagues
    },

    async toggle(leagueId, leagueInfo) {
      if (this.ids.includes(leagueId)) {
        await followApi.unfollow(leagueId)
        this.ids = this.ids.filter((id) => id !== leagueId)
        this.leagues = this.leagues.filter((l) => l.id !== leagueId)
        this.filterIds = this.filterIds.filter((id) => id !== leagueId)
        const nextMap = { ...this.childMap }
        delete nextMap[leagueId]
        this.childMap = nextMap
        return false
      }
      const res = await followApi.follow(leagueId)
      if (!this.ids.includes(leagueId)) {
        this.ids = [...this.ids, leagueId]
        const item = res?.league || leagueInfo || { id: leagueId }
        if (!this.leagues.some((l) => l.id === leagueId)) {
          this.leagues = [...this.leagues, item]
        }
      }
      await this.fetch()
      return true
    },
  },
})
