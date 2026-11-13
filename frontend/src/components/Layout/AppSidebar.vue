<template>
  <aside class="app-sidebar">
    <nav class="sidebar-nav">
      <div v-for="group in menuGroups" :key="group.label" class="nav-group">
        <div class="nav-group-label">{{ group.label }}</div>
        <router-link
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
          <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
        </router-link>
      </div>
    </nav>

    <div class="sidebar-footer">
      <div class="model-status">
        <div class="status-header">
          <span class="status-dot"></span>
          <span class="status-text">{{ modelStatus.status === 'running' ? '模型运行中' : '模型待命' }}</span>
        </div>
        <div class="status-info">
          <div class="status-row">
            <span class="text-muted text-sm">版本</span>
            <span class="text-blue text-sm">{{ modelStatus.version }}</span>
          </div>
          <div class="status-row">
            <span class="text-muted text-sm">模拟次数</span>
            <span class="text-green text-sm">{{ modelStatus.simulations }}</span>
          </div>
          <div class="status-row">
            <span class="text-muted text-sm">融合权重</span>
            <span class="text-gold text-sm">{{ modelStatus.weightsLabel }}</span>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { matchApi, riskApi, modelApi } from '@/api'
import { hasAnyPermission } from '@/utils/permissions'
import { useUserStore } from '@/stores/user'
import { useFollowsStore } from '@/stores/follows'

const route = useRoute()
const userStore = useUserStore()
const followsStore = useFollowsStore()
const upcomingCount = ref(0)
const highRiskCount = ref(0)
const modelStatus = ref({
  status: 'running',
  version: '-',
  simulations: '10,000',
  weightsLabel: '-',
})

const BADGE_TTL_MS = 60 * 1000
let badgesCachedAt = 0
let badgesLoading = null

const allMenuGroups = [
  {
    label: '数据分析',
    items: [
      { path: '/', label: '首页', icon: '🏠', perms: ['dashboard:view'] },
      { path: '/matches', label: '赛事', icon: '⚽', perms: ['match:upcoming', 'match:finished', 'match:manage'], badgeKey: 'upcoming' },
      { path: '/leagues', label: '联赛列表', icon: '🏆', perms: ['league:view', 'league:manage'] },
      { path: '/simulation', label: '模拟预测', icon: '🎲', perms: ['simulation:view', 'model:manage'] },
      { path: '/simulation-bets', label: '我的模拟投注', icon: '📝', perms: ['simulation:view'] },
    ],
  },
  {
    label: '竞彩足球',
    items: [
      { path: '/jingcai-live', label: '竞彩比分', icon: '📋', perms: ['match:jingcai_live', 'jingcai:manage', 'match:manage'] },
      { path: '/jingcai', label: '竞彩分析', icon: '🎯', perms: ['match:jingcai_bf', 'match:jingcai_bf_history', 'jingcai:manage', 'match:upcoming', 'match:finished', 'match:manage'] },
      { path: '/jingcai-bf-summary', label: '分析汇总', icon: '📈', perms: ['match:jingcai_bf_summary', 'jingcai:manage', 'match:jingcai_bf_history', 'match:finished', 'match:manage'] },
      // 竞彩足球全玩法列表（trade.500.com/jczq，视图内可切换 单关/胜平负/让球/混合过关/比分/进球数/半全场）
      { path: '/jingcai-trade', label: '竞足列表', icon: '🎫', perms: ['jingcai:config', 'jingcai:manage', 'match:jingcai_bf'] },
    ],
  },
  {
    label: '模型中心',
    items: [
      { path: '/model', label: '模型管理', icon: '🧠', perms: ['model:manage'] },
      { path: '/risk', label: '风控体系', icon: '🛡️', perms: ['risk:manage'], badgeKey: 'risk' },
    ],
  },
  {
    label: '系统运维',
    items: [
      { path: '/schedule', label: '定时任务', icon: '⏰', perms: ['schedule:manage'] },
      { path: '/league-manage', label: '联赛管理', icon: '⚙️', perms: ['league:config', 'league:manage'] },
    ],
  },
  {
    label: '系统管理',
    items: [
      { path: '/users', label: '用户管理', icon: '👥', perms: ['user:manage'] },
      { path: '/permissions', label: '角色权限', icon: '🔐', perms: ['role:manage'] },
      { path: '/profile', label: '个人中心', icon: '👤', perms: ['profile:view'] },
    ],
  },
]

const menuGroups = computed(() => {
  return allMenuGroups
    .map((group) => ({
      ...group,
      items: group.items
        .filter((item) => hasAnyPermission(...(item.perms || [])))
        .map((item) => ({
          path: item.path,
          label: item.label,
          icon: item.icon,
          badge:
            item.badgeKey === 'upcoming'
              ? upcomingCount.value || null
              : item.badgeKey === 'risk'
                ? highRiskCount.value || null
                : null,
        })),
    }))
    .filter((group) => group.items.length > 0)
})

function isActive(path) {
  if (path === '/') return route.path === '/'
  if (route.path === path) return true
  return route.path.startsWith(`${path}/`)
}

async function loadBadges(force = false) {
  if (!force && badgesCachedAt && Date.now() - badgesCachedAt < BADGE_TTL_MS) return
  if (badgesLoading) return badgesLoading

  badgesLoading = (async () => {
    try {
      const upcomingParams = { page: 1, page_size: 1 }
      if (!userStore.isAdmin) {
        await followsStore.ensureLoaded()
        upcomingParams.league_ids = followsStore.queryIds.join(',')
      }
      const upcoming = await matchApi.getUpcoming(upcomingParams)
      upcomingCount.value = upcoming?.pagination?.total || 0
    } catch (_) {
      upcomingCount.value = 0
    }
    try {
      const riskParams = userStore.isAdmin
        ? {}
        : { followed_only: true, include_children: followsStore.includeChildren }
      const risks = await riskApi.getByLevel('high', riskParams)
      const list = risks?.alerts || []
      highRiskCount.value = list.filter((r) => !r.is_processed).length || list.length
    } catch (_) {
      highRiskCount.value = 0
    }
    try {
      const status = await modelApi.getStatus()
      const sims = status?.models_detail?.find((m) => m.key === 'monte_carlo')?.key_params?.simulations
      const w = status?.weights || {}
      const weightsLabel = ['elo', 'poisson', 'monte_carlo']
        .filter((k) => w[k] != null)
        .map((k) => `${k[0].toUpperCase()}${Math.round(Number(w[k]) * 100)}`)
        .join('/')
      modelStatus.value = {
        status: status?.status || 'running',
        version: status?.version || '-',
        simulations: sims ? Number(sims).toLocaleString() : '10,000',
        weightsLabel: weightsLabel || '-',
      }
    } catch (_) {
      /* keep defaults */
    }
    badgesCachedAt = Date.now()
    badgesLoading = null
  })()

  return badgesLoading
}

onMounted(() => loadBadges())
</script>

<style scoped>
.app-sidebar {
  width: 200px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

.nav-group {
  margin-bottom: 8px;
}

.nav-group-label {
  padding: 8px 16px 4px;
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  color: var(--text-secondary);
  transition: var(--transition);
  border-left: 3px solid transparent;
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: rgba(var(--color-blue-rgb), 0.1);
  color: var(--color-blue);
  border-left-color: var(--color-blue);
}

.nav-icon {
  font-size: 16px;
  width: 22px;
  text-align: center;
}

.nav-label {
  flex: 1;
  font-size: 13px;
}

.nav-badge {
  background: var(--color-red);
  color: #fff;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 10px;
  font-weight: 700;
  min-width: 18px;
  text-align: center;
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--border-color);
}

.model-status {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
}

.status-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-green);
  box-shadow: 0 0 6px var(--color-green);
}

.status-text {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.status-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.status-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
