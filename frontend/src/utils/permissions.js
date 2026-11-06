import { useUserStore } from '@/stores/user'

/** 路由/菜单权限码，与 init_db 菜单权限对齐；同页多权限码为"或"关系（合并页继承各旧入口权限） */
export const ROUTE_PERMISSIONS = {
  Dashboard: ['dashboard:view'],
  Matches: ['match:upcoming', 'match:finished', 'match:manage'],
  JingcaiAnalysis: [
    'match:jingcai_bf', 'match:jingcai_bf_history', 'jingcai:manage',
    'match:upcoming', 'match:finished', 'match:manage',
  ],
  JingcaiLiveScore: ['match:jingcai_live', 'jingcai:manage', 'match:manage'],
  JingcaiBfSummary: ['match:jingcai_bf_summary', 'jingcai:manage', 'match:jingcai_bf_history', 'match:finished', 'match:manage'],
  MatchDetail: ['match:upcoming', 'match:finished', 'match:jingcai_bf', 'match:jingcai_bf_history', 'jingcai:manage', 'match:manage'],
  LeagueList: ['league:view', 'league:manage'],
  LeagueManage: ['league:config', 'league:manage'],
  TeamDetail: ['league:view', 'league:manage', 'match:upcoming', 'match:finished'],
  Simulation: ['simulation:view', 'model:manage'],
  ModelManage: ['model:manage'],
  RiskControl: ['risk:manage'],
  ScheduleManage: ['schedule:manage'],
  UserManage: ['user:manage'],
  PermissionManage: ['role:manage'],
  Profile: ['profile:view'],
}

export function hasAnyPermission(...codes) {
  const store = useUserStore()
  if (store.isAdmin) return true
  const perms = store.permissions || []
  // 旧会话未带回权限码时不锁死菜单，避免升级后无法进入
  if (!perms.length) return true
  if (!codes.length) return true
  const set = new Set(perms)
  return codes.some((c) => set.has(c))
}

export function canAccessRoute(routeName) {
  const required = ROUTE_PERMISSIONS[routeName]
  if (!required) return true
  return hasAnyPermission(...required)
}
