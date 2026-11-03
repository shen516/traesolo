<template>
  <div class="profile">
    <!-- 加载状态 -->
    <div v-if="loading" class="state-block">
      <span class="loading-spinner"></span>
      <span class="state-text">数据加载中...</span>
    </div>

    <!-- 错误提示 -->
    <div v-else-if="errorMsg" class="state-block state-error">
      <span class="state-text">⚠ {{ errorMsg }}</span>
      <button class="btn btn-primary" @click="loadAll">重试</button>
    </div>

    <template v-else>
      <!-- 初始密码未修改软提示：不拦截其它接口，仅提醒 -->
      <div v-if="mustChange && activeTab !== 'password'" class="soft-pwd-hint">
        ⚠ 当前仍在用初始密码，建议尽快修改（右上角头像 → 修改密码）。
      </div>

      <!-- 用户信息卡片 -->
      <section class="card profile-card">
        <div class="profile-main">
          <div class="profile-avatar">{{ userInfo.avatar }}</div>
          <div class="profile-info">
            <div class="profile-name-row">
              <h1 class="profile-name">{{ userInfo.name }}</h1>
              <span class="tag tag-info level-tag">{{ userInfo.level }}</span>
            </div>
            <div class="profile-meta">
              <span class="meta-item">
                <span class="meta-icon">📅</span>
                加入日期：{{ userInfo.joinDate || '—' }}
              </span>
              <span class="meta-item">
                <span class="meta-icon">⚽</span>
                主队：{{ favoriteTeamName }}
              </span>
            </div>
          </div>
        </div>
        <div class="profile-actions">
          <button class="btn btn-sm btn-outline" @click="goPasswordTab">修改密码</button>
        </div>
        <div class="profile-stats">
          <div class="profile-stat" v-for="stat in profileStats" :key="stat.label">
            <span class="profile-stat-value" :style="{ color: stat.color }">{{ stat.value }}</span>
            <span class="profile-stat-label text-muted">{{ stat.label }}</span>
          </div>
        </div>
      </section>

      <!-- 订阅信息 -->
      <section class="card subscription-card">
        <div class="section-header">
          <h2 class="section-title"><span class="section-bar"></span>订阅信息</h2>
          <span class="tag" :class="subscriptionTagClass">{{ subscriptionStatusText }}</span>
        </div>
        <div class="subscription-body">
          <div class="subscription-plan">
            <span class="plan-icon">💎</span>
            <div class="plan-info">
              <span class="plan-name text-gold">{{ subscription.planName || '免费版' }}</span>
              <span class="plan-desc text-muted">{{ tierDesc }}</span>
            </div>
          </div>
          <div class="subscription-detail">
            <div class="detail-row">
              <span class="detail-label text-muted">到期日期</span>
              <span class="detail-value">{{ subscription.expireDate || '不限' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label text-muted">剩余天数</span>
              <span class="detail-value text-green">{{ remainingDaysText }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label text-muted">订阅状态</span>
              <span class="detail-value">
                <span class="status-dot" :class="`status-${subscription.status}`"></span>
                {{ subscriptionStatusText }}
              </span>
            </div>
          </div>
          <button class="btn btn-primary renew-btn" @click="plansVisible = !plansVisible">
            {{ plansVisible ? '收起套餐' : '查看套餐' }}
          </button>
        </div>
        <!-- 当前权益 -->
        <div class="feature-list" v-if="subscription.featureLabels.length">
          <span class="feature-title text-muted">当前权益：</span>
          <span v-for="label in subscription.featureLabels" :key="label" class="tag tag-info tag-sm feature-tag">
            {{ label }}
          </span>
        </div>
        <!-- 套餐一览（无支付，仅展示；开通/续费由管理员操作） -->
        <div v-if="plansVisible" class="plan-grid">
          <div v-for="plan in plans" :key="plan.code" class="plan-card" :class="{ current: plan.code === subscription.planCode }">
            <div class="plan-card-head">
              <span class="plan-card-name">{{ plan.name }}</span>
              <span v-if="plan.code === subscription.planCode" class="tag tag-low tag-sm">当前</span>
            </div>
            <div class="plan-card-price">
              <template v-if="plan.price > 0">¥{{ plan.price }}<span class="plan-duration">/{{ plan.duration_days }}天</span></template>
              <template v-else>免费</template>
            </div>
            <div class="plan-card-desc text-muted">{{ plan.description }}</div>
            <ul class="plan-card-features">
              <li v-for="f in plan.features" :key="f">{{ plan.feature_labels?.[f] || f }}</li>
            </ul>
            <div class="plan-card-tip text-muted">如需开通/续费，请联系管理员</div>
          </div>
        </div>
      </section>

      <!-- 历史分析记录 -->
      <section class="card history-card">
        <div class="section-header">
          <h2 class="section-title"><span class="section-bar"></span>历史分析记录</h2>
          <span class="section-sub text-muted">共 {{ historyRecords.length }} 条</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th class="col-match">赛事</th>
              <th class="col-date">日期</th>
              <th class="col-score">预测比分</th>
              <th class="col-score">实际比分</th>
              <th class="col-result">结果</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in historyRecords" :key="record.id">
              <td class="col-match">{{ record.match }}</td>
              <td class="col-date text-muted">{{ record.date }}</td>
              <td class="col-score">
                <span class="score-tag score-predict">{{ record.prediction }}</span>
              </td>
              <td class="col-score">
                <span class="score-tag score-actual">{{ record.actual }}</span>
              </td>
              <td class="col-result">
                <span class="tag" :class="resultTagClass(record.result)">
                  {{ resultText(record.result) }}
                </span>
              </td>
            </tr>
            <tr v-if="!historyRecords.length">
              <td colspan="5" class="text-muted" style="text-align:center;padding:24px 0;">
                暂无历史分析记录
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- 密码修改：主动入口（?tab=password）与强制改密共用同一组件 -->
      <PasswordChangeCard v-if="activeTab === 'password'" :must-change="mustChange" />

      <!-- 偏好设置 -->
      <section class="card preference-card">
        <div class="section-header">
          <h2 class="section-title"><span class="section-bar"></span>偏好设置</h2>
        </div>
        <form class="preference-form" @submit.prevent="savePreferences">
          <div class="form-row">
            <div class="form-label">
              <span class="form-label-text">推送通知</span>
              <span class="form-label-desc text-muted">偏好已保存；站内推送通道尚未接入，暂不生效</span>
            </div>
            <label class="switch">
              <input type="checkbox" v-model="preferences.pushNotification" />
              <span class="switch-slider"></span>
            </label>
          </div>

          <div class="form-row">
            <div class="form-label">
              <span class="form-label-text">数据刷新频率</span>
              <span class="form-label-desc text-muted">设置模型数据自动刷新间隔</span>
            </div>
            <select v-model="preferences.refreshRate" class="form-select">
              <option v-for="opt in refreshOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <div class="form-row">
            <div class="form-label">
              <span class="form-label-text">默认联赛</span>
              <span class="form-label-desc text-muted">设置进入赛事列表时的默认联赛</span>
            </div>
            <select v-model="preferences.defaultLeague" class="form-select">
              <option value="">全部联赛</option>
              <option v-for="lg in defaultLeagueOptions" :key="lg.id" :value="lg.id">
                {{ lg.icon || '🏆' }} {{ lg.name }}
              </option>
            </select>
          </div>

          <div class="form-row form-row-block">
            <div class="form-label">
              <span class="form-label-text">关注的联赛</span>
              <span class="form-label-desc text-muted">最多 20 个，可排序；首页与「仅关注」列表按此过滤。下级联赛不占名额。</span>
            </div>
            <div class="follow-manage">
              <label class="filter-check follow-switch">
                <input type="checkbox" v-model="preferences.includeChildren" />
                关注时包含下级联赛（如欧冠带上欧联）
              </label>
              <div v-if="followDraft.length" class="follow-chips">
                <div v-for="(id, idx) in followDraft" :key="id" class="follow-chip">
                  <span>{{ leagueLabel(id) }}</span>
                  <button type="button" class="chip-btn" :disabled="idx === 0" @click="moveFollow(idx, -1)">↑</button>
                  <button type="button" class="chip-btn" :disabled="idx === followDraft.length - 1" @click="moveFollow(idx, 1)">↓</button>
                  <button type="button" class="chip-btn" @click="removeFollow(id)">×</button>
                </div>
              </div>
              <div v-else class="text-muted follow-empty">尚未关注联赛</div>
              <div class="follow-add">
                <select v-model="followToAdd" class="form-select">
                  <option value="">添加联赛</option>
                  <option v-for="lg in availableToFollow" :key="lg.id" :value="lg.id">
                    {{ lg.icon || '🏆' }} {{ lg.name }}
                  </option>
                </select>
                <button type="button" class="btn btn-sm" :disabled="!followToAdd || followDraft.length >= 20" @click="addFollow">添加</button>
                <button type="button" class="btn btn-sm btn-outline" @click="goFollowedPage">关注专页</button>
              </div>
            </div>
          </div>

          <div class="form-actions">
            <button type="button" class="btn" @click="resetPreferences">重置</button>
            <button type="submit" class="btn btn-primary" :disabled="prefSaving">
              {{ prefSaving ? '保存中...' : '保存设置' }}
            </button>
          </div>
          <p v-if="prefMsg" class="text-muted" style="margin-top:8px;">{{ prefMsg }}</p>
        </form>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { userApi, historyApi, favoriteApi, leagueApi, subscriptionApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { useFollowsStore } from '@/stores/follows'
import PasswordChangeCard from '@/components/PasswordChangeCard.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const followsStore = useFollowsStore()
const followDraft = ref([])
const followToAdd = ref('')
const loading = ref(false)
const errorMsg = ref('')

// 初始密码未修改（出厂弱口令）：仅软提示，不再拦截其它接口
const mustChange = computed(() => !!userStore.mustChangePassword)
const activeTab = computed(() => route.query.tab === 'password' ? 'password' : 'main')

// 主动修改密码入口：跳转到 /profile?tab=password（与强制改密共用表单）
function goPasswordTab() {
  router.push({ path: '/profile', query: { tab: 'password' } })
}

// 用户信息（映射为模板所需结构）
const userInfo = ref({
  avatar: '',
  name: '',
  level: '',
  joinDate: '',
  totalAnalysis: 0,
  favoriteTeam: '',
})

// 订阅快照（来自 /subscription/my）
const subscription = ref({
  planCode: 'free',
  planName: '免费版',
  tier: 'free',
  expireDate: '',
  remainingDays: null,
  status: 'active',
  featureLabels: [],
})
const plans = ref([])
const plansVisible = ref(false)

const historyRecords = ref([])
const accuracyRate = ref(0)
const favoriteCount = ref(0)
const leagues = ref([])

const favoriteTeamName = computed(() => userInfo.value.favoriteTeam || '未设置')

const followDraftLeagues = computed(() => {
  return followDraft.value
    .map((id) => leagues.value.find((l) => l.id === id) || followsStore.leagues.find((l) => l.id === id) || { id, name: id, icon: '🏆' })
})

const defaultLeagueOptions = computed(() => {
  if (followDraft.value.length) return followDraftLeagues.value
  return leagues.value
})

const availableToFollow = computed(() => {
  const used = new Set(followDraft.value)
  return leagues.value.filter((l) => !used.has(l.id))
})

function leagueLabel(id) {
  const item = leagues.value.find((l) => l.id === id) || followsStore.leagues.find((l) => l.id === id)
  if (!item) return id
  const inactive = item.is_active === false ? ' · 已停用' : ''
  return `${item.icon || '🏆'} ${item.name}${inactive}`
}

function addFollow() {
  if (!followToAdd.value || followDraft.value.includes(followToAdd.value) || followDraft.value.length >= 20) return
  followDraft.value = [...followDraft.value, followToAdd.value]
  followToAdd.value = ''
}

function removeFollow(id) {
  followDraft.value = followDraft.value.filter((item) => item !== id)
  if (preferences.value.defaultLeague === id) preferences.value.defaultLeague = ''
}

function moveFollow(idx, delta) {
  const next = idx + delta
  if (next < 0 || next >= followDraft.value.length) return
  const copy = [...followDraft.value]
  const [item] = copy.splice(idx, 1)
  copy.splice(next, 0, item)
  followDraft.value = copy
}

function goFollowedPage() {
  router.push('/followed')
}

const correctRate = computed(() => accuracyRate.value || 0)

const profileStats = computed(() => [
  { label: '总分析次数', value: userInfo.value.totalAnalysis, color: 'var(--color-blue)' },
  { label: '正确率', value: correctRate.value + '%', color: 'var(--color-green)' },
  { label: '收藏赛事', value: favoriteCount.value, color: 'var(--color-gold)' }
])

const subscriptionStatusText = computed(() => {
  return { active: '使用中', expired: '已过期', cancelled: '已取消' }[subscription.value.status] || '已过期'
})

const subscriptionTagClass = computed(() => {
  return { active: 'tag-low', expired: 'tag-high', cancelled: 'tag-mid' }[subscription.value.status] || 'tag-high'
})

const tierDesc = computed(() => {
  return { free: '基础胜平负预测', pro: '完整预测与竞彩比分', flagship: '全部高级分析功能' }[subscription.value.tier] || ''
})

const remainingDaysText = computed(() => {
  if (subscription.value.tier === 'free') return '不限'
  if (subscription.value.remainingDays == null) return '—'
  return `${subscription.value.remainingDays} 天`
})

const refreshOptions = [
  { value: 'realtime', label: '实时' },
  { value: '5min', label: '每 5 分钟' },
  { value: '15min', label: '每 15 分钟' },
  { value: '30min', label: '每 30 分钟' },
  { value: '1hour', label: '每 1 小时' }
]

const preferences = ref({
  pushNotification: true,
  refreshRate: '15min',
  defaultLeague: '',
  includeChildren: false,
})
const prefSaving = ref(false)
const prefMsg = ref('')

function resultText(result) {
  return { correct: '正确', partial: '部分正确', wrong: '错误' }[result] || result || '—'
}

function resultTagClass(result) {
  return { correct: 'tag-low', partial: 'tag-mid', wrong: 'tag-high' }[result] || 'tag-info'
}

function deriveAvatar(user) {
  if (user.avatar) return user.avatar
  const name = user.username || ''
  return name.slice(0, 2).toUpperCase()
}

async function savePreferences() {
  prefMsg.value = ''
  const userId = userStore.user?.id
  if (!userId) {
    prefMsg.value = '未登录'
    return
  }
  prefSaving.value = true
  try {
    if (preferences.value.defaultLeague && followDraft.value.length && !followDraft.value.includes(preferences.value.defaultLeague)) {
      preferences.value.defaultLeague = followDraft.value[0] || ''
    }
    followsStore.persistIncludeChildren(preferences.value.includeChildren)
    await Promise.all([
      userApi.updatePreferences(userId, {
        push_notification: preferences.value.pushNotification,
        refresh_rate: preferences.value.refreshRate,
        default_league_id: preferences.value.defaultLeague || '',
        follow_include_children: !!preferences.value.includeChildren,
      }),
      followsStore.replace(followDraft.value),
    ])
    prefMsg.value = preferences.value.pushNotification
      ? '已保存（推送通道尚未接入，其余偏好已生效）'
      : '偏好已保存'
  } catch (e) {
    prefMsg.value = e?.message || '保存失败'
  } finally {
    prefSaving.value = false
  }
}

function resetPreferences() {
  preferences.value = {
    pushNotification: false,
    refreshRate: '15min',
    defaultLeague: '',
    includeChildren: followsStore.includeChildren,
  }
  followDraft.value = [...followsStore.ids]
}

async function loadAll() {
  loading.value = true
  errorMsg.value = ''
  try {
    const userId = userStore.user?.id
    if (!userId) {
      throw new Error('未获取到用户信息，请重新登录')
    }

    const [userDetail, historyRes, accuracyRes, favoriteRes, leagueRes, prefRes, subRes, plansRes] = await Promise.all([
      userApi.getById(userId),
      historyApi.getByUser(userId),
      historyApi.getAccuracy(userId),
      favoriteApi.getByUser(userId),
      leagueApi.getAll(),
      userApi.getPreferences(userId).catch(() => null),
      subscriptionApi.getMy().catch(() => null),
      subscriptionApi.getPlans().catch(() => null),
      followsStore.ensureLoaded(),
    ])
    followDraft.value = [...followsStore.ids]

    if (prefRes) {
      preferences.value = {
        pushNotification: !!prefRes.push_notification,
        refreshRate: prefRes.refresh_rate || '15min',
        defaultLeague: prefRes.default_league_id || '',
        includeChildren: !!prefRes.follow_include_children,
      }
      followsStore.persistIncludeChildren(preferences.value.includeChildren)
    }

    if (subRes) {
      subscription.value = {
        planCode: subRes.plan_code || 'free',
        planName: subRes.plan_name || '免费版',
        tier: subRes.tier || 'free',
        expireDate: subRes.expire_date || '',
        remainingDays: subRes.remaining_days,
        status: subRes.status || 'active',
        featureLabels: Object.values(subRes.feature_labels || {}),
      }
    }
    plans.value = plansRes?.plans || []

    userInfo.value = {
      avatar: deriveAvatar(userDetail),
      name: userDetail.username || '',
      level: userDetail.level || '',
      joinDate: userDetail.join_date || '',
      totalAnalysis: userDetail.total_analysis || 0,
      favoriteTeam: userDetail.favorite_team_id || '',
    }

    historyRecords.value = (historyRes.history || []).map(h => ({
      id: h.id,
      match: h.match_name || h.match_id || '—',
      date: h.created_at ? String(h.created_at).slice(0, 10) : '',
      prediction: h.prediction || '—',
      actual: h.actual || '—',
      result: h.result || ''
    }))

    accuracyRate.value = Math.round(accuracyRes.accuracy_rate || 0)
    favoriteCount.value = (favoriteRes.favorites || []).length
    leagues.value = leagueRes.leagues || []
  } catch (e) {
    errorMsg.value = e.message || '数据加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadAll()
})
</script>

<style scoped>
.profile {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  overflow-y: auto;
  max-width: 1100px;
  margin: 0 auto;
}

/* 初始密码未修改软提示 */
.soft-pwd-hint {
  padding: 10px 14px;
  background: rgba(var(--color-gold-rgb), 0.12);
  border: 1px solid rgba(var(--color-gold-rgb), 0.3);
  border-radius: var(--radius-sm);
  color: var(--color-gold);
  font-size: 13px;
  line-height: 1.6;
}

/* 用户信息卡片 */
.profile-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-secondary) 100%);
}

.profile-main {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-shrink: 0;
}

/* 主动改密入口 */
.profile-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.profile-avatar {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--color-blue), #0066cc);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  font-weight: 700;
  color: #fff;
  box-shadow: 0 0 20px rgba(var(--color-blue-rgb), 0.3);
}

.profile-info {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.profile-name-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.profile-name {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.level-tag {
  font-size: 12px;
  padding: 3px 12px;
}

.profile-meta {
  display: flex;
  gap: 20px;
}

.meta-item {
  font-size: 13px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.meta-icon {
  font-size: 14px;
}

.profile-stats {
  display: flex;
  gap: 32px;
  padding: 0 12px;
}

.profile-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.profile-stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

.profile-stat-label {
  font-size: 12px;
}

/* 区块通用 */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.section-bar {
  display: inline-block;
  width: 4px;
  height: 16px;
  background: var(--color-blue);
  border-radius: 2px;
}

.section-sub {
  font-size: 12px;
}

/* 订阅信息 */
.subscription-body {
  display: flex;
  align-items: center;
  gap: 32px;
  flex-wrap: wrap;
}

.subscription-plan {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 14px 18px;
  min-width: 200px;
}

.plan-icon {
  font-size: 30px;
}

.plan-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.plan-name {
  font-size: 18px;
  font-weight: 700;
}

.plan-desc {
  font-size: 12px;
}

.subscription-detail {
  display: flex;
  gap: 28px;
  flex: 1;
  min-width: 260px;
}

.detail-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 11px;
}

.detail-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.status-active {
  background: var(--color-green);
  box-shadow: 0 0 8px var(--color-green);
}

.status-dot.status-expired {
  background: var(--color-red);
}

.status-dot.status-cancelled {
  background: var(--color-orange);
}

.renew-btn {
  margin-left: auto;
}

/* 权益清单 */
.feature-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px dashed var(--border-color);
}

.feature-title {
  font-size: 12px;
}

.feature-tag {
  font-size: 11px;
}

/* 套餐一览 */
.plan-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.plan-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
}

.plan-card.current {
  border-color: var(--color-gold);
  box-shadow: 0 0 12px rgba(var(--color-gold-rgb), 0.15);
}

.plan-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.plan-card-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.plan-card-price {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-gold);
}

.plan-duration {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 400;
}

.plan-card-desc {
  font-size: 12px;
}

.plan-card-features {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.plan-card-tip {
  font-size: 11px;
  margin-top: auto;
}

/* 历史记录表格 */
.history-card {
  display: flex;
  flex-direction: column;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table thead th {
  text-align: left;
  color: var(--text-muted);
  font-weight: 600;
  padding: 12px 12px;
  border-bottom: 1px solid var(--border-color);
  font-size: 12px;
}

.data-table thead th.col-score,
.data-table thead th.col-result {
  text-align: center;
}

.data-table tbody td {
  padding: 12px 12px;
  border-bottom: 1px solid rgba(30, 58, 95, 0.4);
  color: var(--text-secondary);
  transition: var(--transition);
}

.data-table tbody td.col-match {
  color: var(--text-primary);
  font-weight: 600;
}

.data-table tbody td.col-score,
.data-table tbody td.col-result {
  text-align: center;
}

.data-table tbody tr {
  transition: var(--transition);
}

.data-table tbody tr:hover {
  background: var(--bg-hover);
}

.data-table tbody tr:hover td {
  color: var(--text-primary);
}

.col-date {
  width: 120px;
}

.score-tag {
  display: inline-block;
  padding: 3px 14px;
  border-radius: 6px;
  font-weight: 700;
  font-size: 13px;
}

.score-predict {
  background: rgba(var(--color-blue-rgb), 0.12);
  color: var(--color-blue);
  border: 1px solid rgba(var(--color-blue-rgb), 0.3);
}

.score-actual {
  background: rgba(var(--color-gold-rgb), 0.12);
  color: var(--color-gold);
  border: 1px solid rgba(var(--color-gold-rgb), 0.3);
}

/* 偏好设置 */
.preference-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  border-bottom: 1px solid rgba(30, 58, 95, 0.4);
  gap: 24px;
}

.form-row:last-of-type {
  border-bottom: none;
}

.form-row-block {
  align-items: flex-start;
  flex-direction: column;
}

.follow-manage {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.follow-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.follow-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-primary);
  background: var(--bg-primary);
}

.chip-btn {
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0 2px;
  font-size: 12px;
}

.chip-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.follow-add {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.follow-empty {
  font-size: 12px;
}

.follow-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.form-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-label-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.form-label-desc {
  font-size: 12px;
}

/* 开关 */
.switch {
  position: relative;
  display: inline-block;
  width: 46px;
  height: 24px;
  flex-shrink: 0;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.switch-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 24px;
  transition: var(--transition);
}

.switch-slider::before {
  content: '';
  position: absolute;
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background: var(--text-muted);
  border-radius: 50%;
  transition: var(--transition);
}

.switch input:checked + .switch-slider {
  background: rgba(var(--color-green-rgb), 0.15);
  border-color: var(--color-green);
}

.switch input:checked + .switch-slider::before {
  transform: translateX(22px);
  background: var(--color-green);
  box-shadow: 0 0 8px rgba(var(--color-green-rgb), 0.6);
}

/* 下拉框 */
.form-select {
  min-width: 180px;
  height: 38px;
  padding: 0 32px 0 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: var(--transition);
  appearance: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238a9bb5' stroke-width='3'><path d='M6 9l6 6 6-6'/></svg>");
  background-repeat: no-repeat;
  background-position: right 10px center;
}

.form-select:hover {
  border-color: var(--color-blue);
}

.form-select:focus {
  outline: none;
  border-color: var(--color-blue);
  box-shadow: 0 0 12px rgba(var(--color-blue-rgb), 0.2);
}

.form-select option {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

/* 表单按钮 */
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
}

/* 加载/错误状态 */
.state-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 80px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
}

.state-text {
  font-size: 14px;
  color: var(--text-secondary);
}

.state-error .state-text {
  color: var(--color-red);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(var(--color-blue-rgb), 0.2);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: profile-spin 0.8s linear infinite;
}

@keyframes profile-spin {
  to { transform: rotate(360deg); }
}
</style>
