<template>
  <div class="jingcai-page">
    <div class="page-head card">
      <div class="page-head-main">
        <h1 class="page-title">竞彩分析</h1>
        <p class="page-sub">
          对齐竞彩比分投注区布局；数据来自 trade.500.com/jczq?playid=271，仅供分析，不构成投注建议。
        </p>
      </div>
      <div class="page-head-actions">
        <button
          v-if="mode === 'upcoming' && canRefresh"
          class="btn btn-outline"
          :disabled="refreshing"
          @click="refreshOdds"
        >{{ refreshing ? '刷新中...' : '立即刷新比分赔率' }}</button>
        <button
          v-if="mode === 'history' && canRefresh"
          class="btn btn-outline"
          :disabled="refreshing"
          @click="refreshScores"
        >{{ refreshing ? '回写中...' : '回写赛果' }}</button>
        <button class="btn" @click="openConfig">设置</button>
      </div>
    </div>

    <PageTabs :tabs="modeTabs" :model-value="mode" route-base="/jingcai" />

    <!-- 共享筛选栏 -->
    <div class="filter-bar card">
      <div class="filter-section">
        <span class="filter-label">状态</span>
        <select v-if="mode === 'upcoming'" :value="statusFilter" class="filter-select" @change="onStatusChange">
          <option value="">全部</option>
          <option value="upcoming">未开赛</option>
          <option value="live">进行中</option>
          <option value="finished">已完赛</option>
        </select>
        <select v-else v-model="scoreFilter" class="filter-select" @change="onFilterChange">
          <option value="all">全部历史</option>
          <option value="missing">缺比分 / 未完赛</option>
        </select>
      </div>
      <div class="filter-section">
        <span class="filter-label">日期</span>
        <input
          :value="selectedDate"
          type="date"
          class="date-input"
          @change="onDateChange"
        />
        <button
          v-if="selectedDate"
          type="button"
          class="date-clear"
          @click="clearDate"
        >全部</button>
      </div>
      <div class="filter-section">
        <span class="filter-label">联赛</span>
        <input
          v-model="leagueKeyword"
          class="search-input league-input"
          :placeholder="followedOnly ? '输入关注的联赛' : '输入联赛名称'"
          @keyup.enter="onFilterChange"
        />
      </div>
      <label class="filter-check">
        <input type="checkbox" v-model="followedOnly" @change="onFilterChange" />
        仅关注
      </label>
      <label v-if="followedOnly" class="filter-check">
        <input type="checkbox" :checked="followsStore.includeChildren" @change="onIncludeChildrenChange" />
        含下级
      </label>
      <div class="filter-section search-section">
        <span class="filter-label">球队</span>
        <input
          v-model="searchKeyword"
          class="search-input"
          placeholder="搜索球队..."
          @keyup.enter="onFilterChange"
        />
      </div>
      <button class="btn btn-sm btn-primary" @click="onFilterChange">查询</button>
      <span class="result-hint">
        共 <b>{{ total }}</b> 场
        <template v-if="mode === 'history'">
          · 缺比分 <b class="warn">{{ missingScoreTotal }}</b>
        </template>
      </span>
    </div>

    <StateBlock v-if="loading" type="loading" text="数据加载中..." />
    <StateBlock
      v-else-if="errorMsg"
      type="error"
      :text="errorMsg"
      retry-text="重新加载"
      @retry="loadData"
    />
    <StateBlock
      v-else-if="!matches.length"
      type="empty"
      :text="mode === 'upcoming' ? '暂无竞彩比分数据' : '暂无历史比分数据'"
    >
      <div class="state-extra">
        {{ mode === 'upcoming'
          ? '可点击「立即刷新比分赔率」，或启用定时任务「竞彩比分采集」'
          : '可启用定时任务「竞彩分析历史比分回补」，或先采集比分赔率后再点「回写赛果」' }}
      </div>
    </StateBlock>
    <JingcaiMatchTable
      v-else
      :mode="mode"
      :groups="dateGroups"
      :leagues="leagues"
      @goDetail="goDetail"
    />

    <Pagination
      v-if="!loading && totalPages > 1"
      :page="currentPage"
      :page-size="pageSize"
      :total="total"
      @change="goPage"
    />

    <!-- 配置弹窗（原 JingcaiConfig 页面） -->
    <BaseModal v-model="configVisible" title="竞彩足球配置" width="420px">
      <label class="field-label" for="recommend-count">推荐比分数量</label>
      <div class="field-row">
        <input
          id="recommend-count"
          v-model.number="configCount"
          class="count-input"
          type="number"
          :min="configBounds.min"
          :max="configBounds.max"
          step="1"
        />
        <span class="field-range">{{ configBounds.min }} – {{ configBounds.max }}，默认 {{ configBounds.default }}</span>
      </div>
      <p class="field-hint">
        保存后，比分和历史比分里的历史相似盘口比分推荐，会按这个数量返回。
      </p>
      <p v-if="configError" class="field-error">{{ configError }}</p>
      <p v-else-if="configSaved" class="field-ok">已保存，当前推荐 {{ configCount }} 个比分</p>
      <template #footer>
        <button class="btn" @click="configVisible = false">取消</button>
        <button class="btn btn-primary" :disabled="configSaving" @click="saveConfig">
          {{ configSaving ? '保存中...' : '保存' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
/**
 * 竞彩分析页：比分（在赛）/ 历史比分 双模式合一 + 配置内嵌。
 * 由原 JingcaiBf / JingcaiBfHistory / JingcaiConfig 三页合并。
 * 模式经路由 tab（/jingcai/bf、/jingcai/history）驱动。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { matchApi, scheduleApi } from '@/api'
import { adaptUpcomingMatch, unwrapList } from '@/utils/adapters'
import { getActiveLeagues } from '@/utils/catalogCache'
import { hasAnyPermission } from '@/utils/permissions'
import PageTabs from '@/components/common/PageTabs.vue'
import Pagination from '@/components/common/Pagination.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import BaseModal from '@/components/common/BaseModal.vue'
import JingcaiMatchTable from '@/components/jingcai/JingcaiMatchTable.vue'
import { useUserStore } from '@/stores/user'
import { useFollowsStore } from '@/stores/follows'
import { useListScrollRestore } from '@/composables/useListScrollRestore'

const route = useRoute()
const router = useRouter()
useListScrollRestore()
const userStore = useUserStore()
const followsStore = useFollowsStore()
const followedOnly = ref(!userStore.isAdmin)

const modeTabs = [
  { key: 'bf', label: '比分' },
  { key: 'history', label: '历史比分' },
]

const mode = computed(() => (route.params.tab === 'history' ? 'history' : 'upcoming'))

const matches = ref([])
const leagues = ref([])
const loading = ref(false)
const refreshing = ref(false)
const errorMsg = ref('')
const total = ref(0)
const missingScoreTotal = ref(0)
const currentPage = ref(1)
const pageSize = 50
const leagueKeyword = ref('')
const selectedDate = ref('')
const searchKeyword = ref('')
const statusFilter = ref('upcoming')
const statusTouched = ref(false)
const scoreFilter = ref('all')
let loadSeq = 0

const WEEKDAY = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']

const canRefresh = computed(() => hasAnyPermission('schedule:manage', 'match:manage'))
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

const displayLeagues = computed(() => {
  if (!followedOnly.value || !followsStore.ids.length) return leagues.value
  return leagues.value.filter((l) => followsStore.queryIdSet.has(l.id))
})

const dateGroups = computed(() => {
  const map = new Map()
  for (const m of matches.value) {
    const d = m.date || '未知日期'
    if (!map.has(d)) map.set(d, [])
    map.get(d).push(m)
  }
  return [...map.entries()].map(([date, items]) => ({
    date,
    label: formatDateLabel(date),
    items,
  }))
})

function formatDateLabel(dateStr) {
  if (!dateStr || dateStr === '未知日期') return dateStr
  const dt = new Date(`${dateStr}T00:00:00`)
  if (Number.isNaN(dt.getTime())) return dateStr
  return `${dateStr} ${WEEKDAY[dt.getDay()]}`
}

function matchedLeagueIds() {
  const q = leagueKeyword.value.trim().toLowerCase()
  if (!q) return null
  return displayLeagues.value
    .filter((lg) => {
      const name = String(lg.name || '').toLowerCase()
      const id = String(lg.id || '').toLowerCase()
      return name.includes(q) || id.includes(q)
    })
    .map((lg) => lg.id)
}

function listParams() {
  const params = {
    page: currentPage.value,
    page_size: pageSize,
    view: 'summary',
  }
  const matched = matchedLeagueIds()
  if (matched) {
    params.league_ids = matched.join(',')
  } else if (followedOnly.value) {
    params.league_ids = followsStore.queryIds.join(',')
  }
  if (selectedDate.value) params.match_date = selectedDate.value
  if (searchKeyword.value.trim()) params.keyword = searchKeyword.value.trim()
  if (mode.value === 'upcoming') {
    // 选定日期时，默认「未开赛」会把当天已开赛场次排除，改为查该日全部状态
    const status = selectedDate.value && !statusTouched.value ? '' : statusFilter.value
    if (status) params.status = status
  } else {
    params.missing_score = scoreFilter.value === 'missing'
  }
  return params
}

function onStatusChange(e) {
  statusTouched.value = true
  statusFilter.value = e.target.value
  onFilterChange()
}

function onDateChange(e) {
  selectedDate.value = String(e.target.value || '').slice(0, 10)
  if (mode.value === 'upcoming' && !statusTouched.value) {
    statusFilter.value = selectedDate.value ? '' : 'upcoming'
  }
  onFilterChange()
}

function clearDate() {
  selectedDate.value = ''
  if (mode.value === 'upcoming' && !statusTouched.value) statusFilter.value = 'upcoming'
  onFilterChange()
}

function adaptHistory(raw) {
  const m = adaptUpcomingMatch(raw)
  m.homeGoals = raw.home_goals ?? raw.homeGoals ?? null
  m.awayGoals = raw.away_goals ?? raw.awayGoals ?? null
  m.result = raw.result ?? null
  return m
}

async function loadData() {
  const seq = ++loadSeq
  loading.value = true
  errorMsg.value = ''
  try {
    await followsStore.ensureLoaded()
    if (seq !== loadSeq) return
    if (followedOnly.value && !followsStore.ids.length) {
      matches.value = []
      total.value = 0
      missingScoreTotal.value = 0
      return
    }
    const isHistory = mode.value === 'history'
    const data = isHistory
      ? await matchApi.getJingcaiBfHistory(listParams())
      : await matchApi.getJingcaiBf(listParams())
    if (seq !== loadSeq) return
    const raw = unwrapList(data, 'matches')
    matches.value = raw.map(isHistory ? adaptHistory : adaptUpcomingMatch)
    total.value = data?.pagination?.total ?? matches.value.length
    missingScoreTotal.value = isHistory ? (data?.missing_score_total ?? 0) : 0
  } catch (e) {
    if (seq !== loadSeq) return
    errorMsg.value = e?.response?.data?.detail || e.message || '加载失败'
    matches.value = []
    total.value = 0
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function onFilterChange() {
  currentPage.value = 1
  loadData()
}

async function onIncludeChildrenChange(e) {
  await followsStore.setIncludeChildren(e.target.checked)
  onFilterChange()
}

function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  currentPage.value = p
  loadData()
}

// 模式切换（tab 路由变化）时重置分页重新加载
watch(mode, () => {
  currentPage.value = 1
  errorMsg.value = ''
  loadData()
})

function goDetail(id) {
  router.push({ path: `/match/${id}`, query: { from: mode.value === 'history' ? '/jingcai/history' : '/jingcai/bf' } })
}

async function refreshOdds() {
  if (!canRefresh.value) {
    errorMsg.value = '无采集权限，请联系管理员或到定时任务页执行「竞彩比分采集」'
    return
  }
  refreshing.value = true
  errorMsg.value = ''
  try {
    try {
      await scheduleApi.runJingcaiBfNow()
    } catch {
      await matchApi.refreshJingcaiBf({ days_ahead: 7 })
    }
    await loadData()
  } catch (e) {
    errorMsg.value = e?.response?.data?.detail || e.message || '刷新失败'
  } finally {
    refreshing.value = false
  }
}

async function refreshScores() {
  if (!canRefresh.value) {
    errorMsg.value = '无采集权限，请联系管理员'
    return
  }
  refreshing.value = true
  errorMsg.value = ''
  try {
    const params = { days_back: 7 }
    if (selectedDate.value) params.match_date = selectedDate.value
    await matchApi.refreshJingcaiExpiredScores(params)
    await loadData()
  } catch (e) {
    errorMsg.value = e?.response?.data?.detail || e.message || '回写失败'
  } finally {
    refreshing.value = false
  }
}

// ===== 配置弹窗（原 JingcaiConfig） =====
const configVisible = ref(false)
const configSaving = ref(false)
const configError = ref('')
const configSaved = ref(false)
const configCount = ref(3)
const configBounds = ref({ min: 1, max: 10, default: 3 })

async function openConfig() {
  configVisible.value = true
  configSaved.value = false
  configError.value = ''
  try {
    const data = await matchApi.getJingcaiConfig()
    configCount.value = Number(data?.recommend_score_count) || 3
    configBounds.value = {
      min: Number(data?.min) || 1,
      max: Number(data?.max) || 10,
      default: Number(data?.default) || 3,
    }
  } catch (e) {
    configError.value = e?.message || '加载配置失败'
  }
}

async function saveConfig() {
  configSaved.value = false
  configError.value = ''
  const n = Number(configCount.value)
  const b = configBounds.value
  if (!Number.isInteger(n) || n < b.min || n > b.max) {
    configError.value = `推荐比分数量需在 ${b.min} 到 ${b.max} 之间`
    return
  }
  configSaving.value = true
  try {
    const data = await matchApi.updateJingcaiConfig(n)
    configCount.value = Number(data?.recommend_score_count) || n
    configSaved.value = true
  } catch (e) {
    configError.value = e?.message || '保存失败'
  } finally {
    configSaving.value = false
  }
}

onMounted(async () => {
  try {
    leagues.value = await getActiveLeagues()
  } catch {
    leagues.value = []
  }
  await loadData()
})
</script>

<style scoped>
.jingcai-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 18px 20px;
}

.page-head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.page-title {
  margin: 0 0 6px;
  font-size: 1.35rem;
  color: var(--text-primary);
}

.page-sub {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.9rem;
  line-height: 1.5;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: center;
  padding: 14px 16px;
}

.filter-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}

.filter-label {
  color: var(--text-muted);
  font-size: 0.85rem;
  white-space: nowrap;
}

.filter-select,
.search-input,
.date-input {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 6px;
  padding: 6px 10px;
  min-width: 120px;
  color-scheme: dark;
}

.search-input,
.league-input {
  min-width: 160px;
}

.date-input {
  height: 32px;
}

.date-clear {
  padding: 4px 8px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
}

.result-hint {
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-left: auto;
}

.result-hint b {
  color: var(--color-gold);
}

.result-hint b.warn {
  color: var(--color-orange);
}

.state-extra {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-top: 4px;
}

/* 配置弹窗字段 */
.field-label {
  display: block;
  font-weight: 700;
  margin-bottom: 8px;
}
.field-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.count-input {
  width: 96px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 16px;
}
.field-range,
.field-hint {
  color: var(--text-muted);
  line-height: 1.5;
}
.field-hint {
  margin-top: 10px;
}
.field-error {
  margin-top: 10px;
  color: var(--color-red);
}
.field-ok {
  margin-top: 10px;
  color: var(--color-green);
}

@media (max-width: 768px) {
  .page-head {
    flex-direction: column;
  }
  .result-hint {
    margin-left: 0;
  }
}
</style>
