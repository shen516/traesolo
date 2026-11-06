import { createRouter, createWebHistory } from 'vue-router'
import { canAccessRoute } from '@/utils/permissions'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '首页', icon: 'dashboard', keepAlive: true }
  },
  // ===== 赛事（未来/历史合并页） =====
  {
    path: '/matches',
    redirect: '/matches/upcoming',
  },
  {
    path: '/matches/:tab(upcoming|finished)',
    name: 'Matches',
    component: () => import('@/views/Matches.vue'),
    meta: { title: '赛事', icon: 'matches', keepAlive: true }
  },
  {
    path: '/finished-matches',
    redirect: '/matches/finished',
  },
  // ===== 竞彩分析（比分/历史比分合并页） =====
  {
    path: '/jingcai',
    redirect: '/jingcai/bf',
  },
  {
    path: '/jingcai/:tab(bf|history)',
    name: 'JingcaiAnalysis',
    component: () => import('@/views/JingcaiAnalysis.vue'),
    meta: { title: '竞彩分析', icon: 'jingcai', keepAlive: true }
  },
  {
    path: '/jingcai-live',
    name: 'JingcaiLiveScore',
    component: () => import('@/views/JingcaiLiveScore.vue'),
    meta: { title: '竞彩比分', icon: 'jingcai-live', keepAlive: true }
  },
  // 旧路径兼容重定向
  { path: '/jingcai-odds', redirect: '/jingcai/bf' },
  { path: '/jingcai-expired', redirect: '/jingcai/history' },
  { path: '/jingcai-bf', redirect: '/jingcai/bf' },
  { path: '/jingcai-bf-history', redirect: '/jingcai/history' },
  {
    path: '/jingcai-bf-summary',
    name: 'JingcaiBfSummary',
    component: () => import('@/views/JingcaiBfSummary.vue'),
    meta: { title: '分析汇总', icon: 'jingcai-bf-summary', keepAlive: true }
  },
  { path: '/jingcai-config', redirect: '/jingcai/bf' },
  // ===== 详情页 =====
  {
    path: '/match/:id',
    name: 'MatchDetail',
    component: () => import('@/views/MatchDetail.vue'),
    meta: { title: '赛事详情', hidden: true }
  },
  {
    path: '/team/:id',
    name: 'TeamDetail',
    component: () => import('@/views/TeamDetail.vue'),
    meta: { title: '球队详情', hidden: true }
  },
  // ===== 数据分析 =====
  {
    path: '/leagues',
    name: 'LeagueList',
    component: () => import('@/views/LeagueList.vue'),
    meta: { title: '联赛列表', icon: 'leagues', keepAlive: true }
  },
  {
    path: '/simulation',
    name: 'Simulation',
    component: () => import('@/views/Simulation.vue'),
    meta: { title: '模拟预测', icon: 'simulation' }
  },
  // 旧「我的关注」入口并入首页 tab
  {
    path: '/followed',
    redirect: '/?tab=followed',
  },
  {
    path: '/league-manage',
    name: 'LeagueManage',
    component: () => import('@/views/LeagueManage.vue'),
    meta: { title: '联赛管理', icon: 'league-manage' }
  },
  // ===== 模型中心 =====
  {
    path: '/model',
    redirect: '/model/overview',
  },
  {
    path: '/model/:tab(overview|training|quality|monitor)',
    name: 'ModelManage',
    component: () => import('@/views/ModelManage.vue'),
    meta: { title: '模型管理', icon: 'model' }
  },
  {
    path: '/risk',
    name: 'RiskControl',
    component: () => import('@/views/RiskControl.vue'),
    meta: { title: '风控体系', icon: 'risk' }
  },
  // ===== 系统运维 =====
  {
    path: '/schedule',
    redirect: '/schedule/tasks',
  },
  {
    path: '/schedule/:tab(tasks|logs|runtime)',
    name: 'ScheduleManage',
    component: () => import('@/views/ScheduleManage.vue'),
    meta: { title: '定时任务', icon: 'schedule' }
  },
  // ===== 系统管理 =====
  {
    path: '/users',
    name: 'UserManage',
    component: () => import('@/views/UserManage.vue'),
    meta: { title: '用户管理', icon: 'users' }
  },
  {
    path: '/permissions',
    name: 'PermissionManage',
    component: () => import('@/views/PermissionManage.vue'),
    meta: { title: '角色权限', icon: 'permissions' }
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/Profile.vue'),
    meta: { title: '个人中心', icon: 'profile' }
  },
  // ===== 兜底 =====
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/ErrorPage.vue'),
    meta: { title: '无访问权限', code: 403, public: false }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/ErrorPage.vue'),
    meta: { title: '页面不存在', code: 404 }
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title
    ? `${to.meta.title} - 足球量化分析`
    : '足球纯竞技量化分析工具 5.0 职业版'

  const token = localStorage.getItem('token')

  if (to.meta.public) {
    next()
    return
  }
  if (!token) {
    next({ path: '/login', query: to.path !== '/' ? { redirect: to.fullPath } : undefined })
    return
  }

  if (to.name && !canAccessRoute(to.name)) {
    // 无权限：进入 403 提示页（原为静默回首页）
    if (to.name !== 'Forbidden') {
      next({ path: '/403', replace: true })
      return
    }
  }
  next()
})

export default router
