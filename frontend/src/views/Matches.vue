<template>
  <div class="matches-page">
    <PageTabs :tabs="modeTabs" :model-value="mode" route-base="/matches" />

    <MatchFilterBar
      v-model:league="selectedLeague"
      v-model:date="selectedDate"
      v-model:keyword="searchKeyword"
      v-model:expanded="filtersExpanded"
      v-model:density="cardDensity"
      v-model:category="selectedCategory"
      v-model:country="selectedCountry"
      v-model:followed-only="followedOnly"
      :leagues="filteredLeagues"
      :countries="filteredCountries"
      :categories="categories"
      :category-label="getCategoryLabel"
      :date-mode="mode === 'upcoming' ? 'input' : 'select'"
      :date-min="mode === 'upcoming' ? dateMin : undefined"
      :available-dates="mode === 'upcoming' ? undefined : availableDates"
      @change="onFilterChange"
      @category-change="onCategoryChange"
      @country-change="onCountryChange"
      @clear-date="clearDate"
      @update:density="setCardDensity"
    >
      <template #result>
        共 <span class="result-count">{{ total }}</span> 场
        <template v-if="mode === 'upcoming'">
          · 本页已预测 <span class="result-count">{{ predictedCount }}</span>
          · 未预测 <span class="result-count">{{ unpredictedCount }}</span>
        </template>
        <template v-else>
          · 本页有预测 <span class="result-count">{{ predictedCount }}</span>
          · 赛果命中 <span class="result-count">{{ outcomeHitCount }}</span>
        </template>
      </template>
    </MatchFilterBar>

    <!-- 预测状态工具栏 -->
    <div class="predict-toolbar card">
      <div class="predict-tabs">
        <template v-if="mode === 'upcoming'">
          <button class="pred-tab" :class="{ active: predictFilter === 'all' }" @click="predictFilter = 'all'">全部</button>
          <button class="pred-tab" :class="{ active: predictFilter === 'pending' }" @click="predictFilter = 'pending'">未预测 {{ unpredictedCount }}</button>
          <button class="pred-tab" :class="{ active: predictFilter === 'done' }" @click="predictFilter = 'done'">已预测 {{ predictedCount }}</button>
        </template>
        <template v-else>
          <button class="pred-tab" :class="{ active: predictFilter === 'all' }" @click="predictFilter = 'all'">全部</button>
          <button class="pred-tab" :class="{ active: predictFilter === 'done' }" @click="predictFilter = 'done'">有预测 {{ predictedCount }}</button>
          <button class="pred-tab" :class="{ active: predictFilter === 'hit' }" @click="predictFilter = 'hit'">赛果命中 {{ outcomeHitCount }}</button>
          <button class="pred-tab" :class="{ active: predictFilter === 'pending' }" @click="predictFilter = 'pending'">无预测 {{ unpredictedCount }}</button>
        </template>
      </div>
      <div v-if="mode === 'upcoming'" class="predict-toolbar-actions">
        <span v-if="batchState.running" class="batch-progress">
          {{ batchState.label || '正在计算' }} {{ batchState.current }}/{{ batchState.total }}
        </span>
        <span v-else-if="staleOnPageCount" class="batch-progress stale-hint">
          本页 {{ staleOnPageCount }} 场缺融合细节或版本滞后
        </span>
        <button
          class="btn btn-primary"
          :disabled="!unpredictedCount || batchState.running"
          @click="batchCalculate(false)"
        >{{ batchState.running && batchState.mode === 'missing' ? '计算中...' : '计算本页未预测' }}</button>
        <button
          class="btn btn-outline"
          :disabled="!matches.length || batchState.running"
          :title="staleOnPageCount ? '优先补齐缺 meta / 旧版本，也可强制整页重算' : '按当前模型重算本页预测，写入完整 meta_json'"
          @click="recalculatePage(staleOnPageCount > 0)"
        >{{ batchState.running && batchState.mode === 'recalc' ? '重算中...' : (staleOnPageCount ? `重算本页过期(${staleOnPageCount})` : '按新模型重算本页') }}</button>
      </div>
    </div>

    <UpgradeHint
      v-if="mode === 'history' && historyLimited"
      text="免费版仅展示近 7 天历史赛事，升级专业版解锁全部历史数据"
    />

    <StateBlock v-if="loading" type="loading" text="数据加载中..." />
    <StateBlock
      v-else-if="errorMsg"
      type="error"
      :text="errorMsg"
      retry-text="重新加载"
      @retry="loadData"
    />

    <div v-else-if="filteredMatches.length > 0" class="match-grid">
      <template v-if="mode === 'upcoming'">
        <UpcomingMatchCard
          v-for="match in filteredMatches"
          :key="match.id"
          :match="match"
          :league="resolveLeague(match)"
          :home-team="getTeam(match.homeTeam, match)"
          :away-team="getTeam(match.awayTeam, match)"
          :density="cardDensity"
          :predicting="isPredicting(match.id)"
          :batch-running="batchState.running"
          :error-tip="predictError[match.id] || ''"
          :history="matchPredictionHistory[match.id]"
          :history-expanded="expandedHistory === match.id"
          :history-loading="loadingHistory === match.id"
          @detail="goToDetail"
          @predict="(m, recalc) => calculatePrediction(m, recalc)"
          @toggle-history="toggleHistory"
        />
      </template>
      <template v-else>
        <FinishedMatchCard
          v-for="match in filteredMatches"
          :key="match.id"
          :match="match"
          :league="resolveLeague(match)"
          :home-team="getTeam(match.homeTeam, match)"
          :away-team="getTeam(match.awayTeam, match)"
          :density="cardDensity"
          @detail="goToDetail"
        />
      </template>
    </div>

    <StateBlock v-else type="empty">
      <div class="state-extra">
        {{ skipFollowedQuery ? '关注联赛后，这里只展示这些联赛的赛事' : '请尝试调整筛选条件' }}
      </div>
      <button v-if="skipFollowedQuery" class="btn btn-primary" @click="router.push('/leagues')">
        去关注联赛
      </button>
      <button v-else class="btn btn-primary" @click="resetFilters">
        重置筛选
      </button>
    </StateBlock>

    <Pagination
      v-if="!loading && totalPages > 1"
      :page="currentPage"
      :page-size="pageSize"
      :total="total"
      @change="goPage"
    />
  </div>
</template>

<script setup>
/**
 * 赛事页：未来（upcoming）/ 完赛（finished）双模式合一。
 * 由原 MatchList / FinishedMatches 两页合并，共享筛选、分页与球队/联赛解析。
 * 模式经路由 tab（/matches/upcoming、/matches/finished）驱动。
 */
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { matchApi, predictionApi, modelApi, userApi } from '@/api'
import MatchFilterBar from '@/components/match/MatchFilterBar.vue'
import UpcomingMatchCard from '@/components/match/UpcomingMatchCard.vue'
import FinishedMatchCard from '@/components/match/FinishedMatchCard.vue'
import UpgradeHint from '@/components/UpgradeHint.vue'
import PageTabs from '@/components/common/PageTabs.vue'
import Pagination from '@/components/common/Pagination.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { useUserStore } from '@/stores/user'
import { useFollowsStore } from '@/stores/follows'
import {
  adaptUpcomingMatch,
  adaptFinishedMatch,
  adaptPrediction,
  isOutcomeHit,
  unwrapList,
  teamMapFromMatches,
} from '@/utils/adapters'
import { getActiveLeagues } from '@/utils/catalogCache'
import { useMatchListFilters } from '@/composables/useMatchListFilters'
import { useListScrollRestore } from '@/composables/useListScrollRestore'

const router = useRouter()
const route = useRoute()
useListScrollRestore()
const userStore = useUserStore()
const followsStore = useFollowsStore()

const modeTabs = [
  { key: 'upcoming', label: '未来赛事' },
  { key: 'finished', label: '历史赛事' },
]

const mode = computed(() => (route.params.tab === 'finished' ? 'finished' : 'upcoming'))

const {
  followedOnly,
  skipFollowedQuery,
  selectedCategory,
  selectedCountry,
  selectedLeague,
  selectedDate,
  searchKeyword,
  predictFilter,
  filtersExpanded,
  cardDensity,
  currentPage,
  pageSize,
  total,
  totalPages,
  leagues,
  categories,
  filteredCountries,
  filteredLeagues,
  getCategoryLabel,
  getLeague,
  applyPagination,
  listQueryParams,
} = useMatchListFilters({ initialDate: 'all' })

searchKeyword.value = route.query.q || ''

const dateMin = (() => {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
})()

const matches = ref([])
const teamMap = ref(new Map())
const loading = ref(false)
const errorMsg = ref('')
const availableDates = ref([])
const historyLimited = ref(false)

function setCardDensity(mode) {
  if (cardDensity.value === mode) return
  cardDensity.value = mode
  localStorage.setItem('matchCardDensity', mode)
  loadData()
}

function clearDate() {
  if (!selectedDate.value) return
  selectedDate.value = mode.value === 'finished' ? 'all' : ''
  onFilterChange()
}

function onCategoryChange() {
  selectedCountry.value = 'all'
  selectedLeague.value = 'all'
  onFilterChange()
}

function onCountryChange() {
  selectedLeague.value = 'all'
  onFilterChange()
}

function onFilterChange() {
  currentPage.value = 1
  loadData()
}

function goPage(page) {
  if (page >= 1 && page <= totalPages.value && page !== currentPage.value) {
    currentPage.value = page
    loadData()
  }
}

// ===== 预测计算（仅 upcoming 模式使用） =====
const predictingIds = ref({})
const predictError = ref({})
const batchState = ref({ running: false, current: 0, total: 0, mode: '', label: '' })
const currentModelVersion = ref('')
const matchPredictionHistory = ref({})
const expandedHistory = ref(null)
const loadingHistory = ref(null)

const filteredMatches = computed(() => {
  return matches.value.filter((m) => {
    if (predictFilter.value === 'pending' && m.prediction.hasPrediction) return false
    if (predictFilter.value === 'done' && !m.prediction.hasPrediction) return false
    if (predictFilter.value === 'hit' && !isOutcomeHit(m)) return false
    return true
  })
})

const predictedCount = computed(() => matches.value.filter((m) => m.prediction.hasPrediction).length)
const unpredictedCount = computed(() => matches.value.filter((m) => !m.prediction.hasPrediction).length)
const outcomeHitCount = computed(() => matches.value.filter((m) => isOutcomeHit(m)).length)

function isStalePrediction(p) {
  if (!p?.hasPrediction) return false
  if (!p.weightSource) return true
  if (!p.primaryScenario) return true
  if (currentModelVersion.value && p.modelVersion && p.modelVersion !== currentModelVersion.value) {
    return true
  }
  return false
}

const staleOnPageCount = computed(() =>
  matches.value.filter((m) => isStalePrediction(m.prediction)).length
)

function isPredicting(id) {
  return !!predictingIds.value[id]
}

function getTeam(id, match) {
  if (match?.homeTeam === id && match.homeTeamInfo) return match.homeTeamInfo
  if (match?.awayTeam === id && match.awayTeamInfo) return match.awayTeamInfo
  return teamMap.value.get(id) || { name: '未知', short: '未知', logo: '⚪' }
}

function resolveLeague(match) {
  return match.leagueInfo || getLeague(match.league)
}

async function loadData() {
  loading.value = true
  errorMsg.value = ''
  try {
    await followsStore.ensureLoaded()
    if (skipFollowedQuery.value) {
      matches.value = []
      applyPagination({ pagination: { total: 0, pages: 0 } }, 0)
      availableDates.value = []
      leagues.value = await getActiveLeagues()
      return
    }
    const isFinished = mode.value === 'finished'
    const [matchesRes, leagueList] = await Promise.all([
      isFinished
        ? matchApi.getFinished({
            ...listQueryParams(),
            match_date: selectedDate.value === 'all' ? undefined : selectedDate.value,
          })
        : matchApi.getUpcoming({
            ...listQueryParams(),
            match_date: selectedDate.value === 'all' || !selectedDate.value ? undefined : selectedDate.value,
          }),
      getActiveLeagues(),
    ])

    const rawMatches = unwrapList(matchesRes, 'matches')
    matches.value = rawMatches.map(isFinished ? adaptFinishedMatch : adaptUpcomingMatch)
    applyPagination(matchesRes, matches.value.length)
    historyLimited.value = !!matchesRes?.history_limited

    if (isFinished) {
      const dates = Array.isArray(matchesRes?.available_dates) ? matchesRes.available_dates : []
      availableDates.value = dates
      const needDateReset =
        selectedDate.value !== 'all' && !dates.includes(selectedDate.value)
      if (needDateReset) {
        selectedDate.value = 'all'
        currentPage.value = 1
        loading.value = false
        await loadData()
        return
      }
    }

    leagues.value = leagueList
    teamMap.value = teamMapFromMatches(matches.value)
  } catch (err) {
    if (err?.code === 'FEATURE_LOCKED') {
      historyLimited.value = true
      selectedDate.value = 'all'
      currentPage.value = 1
      errorMsg.value = ''
      loading.value = false
      await loadData()
      return
    }
    errorMsg.value = err?.message || '加载数据失败，请检查后端服务'
  } finally {
    loading.value = false
  }
}

// 模式切换（tab 路由变化）时重置分页与预测筛选重新加载
watch(mode, () => {
  currentPage.value = 1
  predictFilter.value = 'all'
  selectedDate.value = 'all'
  errorMsg.value = ''
  loadData()
})

// ===== 预测操作（upcoming 模式） =====
function applyPrediction(matchId, result) {
  const prediction = adaptPrediction(result)
  const matchIndex = matches.value.findIndex((m) => m.id === matchId)
  if (matchIndex !== -1) {
    matches.value[matchIndex].prediction = prediction
  }
}

function goToDetail(id) {
  router.push(`/match/${id}`)
}

async function calculatePrediction(match, recalculate = false) {
  predictingIds.value = { ...predictingIds.value, [match.id]: true }
  delete predictError.value[match.id]
  try {
    const result = await matchApi.getPrediction(match.id, recalculate)
    applyPrediction(match.id, result)
    if (recalculate) await refreshHistoryIfOpen(match.id)
  } catch (err) {
    predictError.value[match.id] = err?.message || '预测计算失败'
  } finally {
    const next = { ...predictingIds.value }
    delete next[match.id]
    predictingIds.value = next
  }
}

async function refreshHistoryIfOpen(matchId) {
  delete matchPredictionHistory.value[matchId]
  if (expandedHistory.value === matchId) {
    expandedHistory.value = null
    await toggleHistory(matchId)
  }
}

async function batchCalculate(recalculate = false) {
  const targets = recalculate
    ? matches.value
    : matches.value.filter(m => !m.prediction.hasPrediction)
  if (!targets.length || batchState.value.running) return
  batchState.value = {
    running: true,
    current: 0,
    total: targets.length,
    mode: recalculate ? 'recalc' : 'missing',
    label: recalculate ? '正在重算' : '正在计算',
  }
  try {
    const res = await predictionApi.batchCalculate(targets.map(m => m.id), recalculate)
    const list = res?.predictions || []
    list.forEach(item => {
      if (item?.match_id) applyPrediction(item.match_id, item)
    })
    batchState.value.current = list.length
    const failedN = (res?.failed || []).length
    if (failedN) {
      errorMsg.value = `计算完成：成功 ${res?.calculated ?? list.length}，失败 ${failedN}`
    }
    if (recalculate) {
      for (const m of targets) await refreshHistoryIfOpen(m.id)
    }
  } catch (err) {
    for (let i = 0; i < targets.length; i++) {
      batchState.value.current = i + 1
      await calculatePrediction(targets[i], recalculate)
    }
    if (!targets.length) {
      errorMsg.value = err?.message || '批量计算失败'
    }
  } finally {
    batchState.value = { running: false, current: 0, total: 0, mode: '', label: '' }
  }
}

async function recalculatePage(onlyStale = false) {
  if (!matches.value.length || batchState.value.running) return
  const ids = onlyStale
    ? matches.value.filter(m => !m.prediction.hasPrediction || isStalePrediction(m.prediction)).map(m => m.id)
    : matches.value.map(m => m.id)
  if (!ids.length) return
  batchState.value = {
    running: true,
    current: 0,
    total: ids.length,
    mode: 'recalc',
    label: onlyStale ? '补齐过期' : '按新模型重算',
  }
  try {
    const res = await predictionApi.recalculate({
      scope: 'ids',
      match_ids: ids,
      only_stale: onlyStale,
      include_unpredicted: true,
      limit: Math.max(ids.length, 20),
    })
    const list = res?.predictions || []
    list.forEach(item => {
      if (item?.match_id) applyPrediction(item.match_id, item)
    })
    batchState.value.current = list.length
    if (res?.model_version) currentModelVersion.value = res.model_version
    for (const id of ids) await refreshHistoryIfOpen(id)
  } catch (err) {
    try {
      const res = await predictionApi.batchCalculate(ids, true)
      ;(res?.predictions || []).forEach(item => {
        if (item?.match_id) applyPrediction(item.match_id, item)
      })
    } catch (e2) {
      errorMsg.value = e2?.message || err?.message || '重算失败'
    }
  } finally {
    batchState.value = { running: false, current: 0, total: 0, mode: '', label: '' }
  }
}

async function toggleHistory(matchId) {
  if (expandedHistory.value === matchId) {
    expandedHistory.value = null
    return
  }
  expandedHistory.value = matchId
  loadingHistory.value = matchId
  try {
    const result = await matchApi.getPredictionHistory(matchId)
    const history = result.history || []
    matchPredictionHistory.value[matchId] = history.map((h) => ({
      ...adaptPrediction(h),
      id: h.id,
      created_at: h.created_at || h.createdAt || '',
    }))
  } catch (err) {
    console.error('加载历史记录失败:', err)
    matchPredictionHistory.value[matchId] = []
  } finally {
    loadingHistory.value = null
  }
}

function resetFilters() {
  selectedCategory.value = 'all'
  selectedCountry.value = 'all'
  selectedLeague.value = 'all'
  selectedDate.value = 'all'
  searchKeyword.value = ''
  predictFilter.value = 'all'
  onFilterChange()
}

// ===== 自动刷新（upcoming 模式用户偏好） =====
const refreshTimer = ref(null)
const preferenceRefreshMs = ref(0)

async function applyUserPreferences() {
  try {
    const userId = userStore.user?.id
    if (!userId) return
    const pref = await userApi.getPreferences(userId)
    const lid = pref?.default_league_id
    if (lid) selectedLeague.value = lid
    const mins = Number(pref?.refresh_interval || 0)
    if (mins > 0) {
      preferenceRefreshMs.value = Math.max(60, mins) * 60 * 1000
    }
  } catch (_) {
    /* 偏好可选 */
  }
}

function startAutoRefresh() {
  stopAutoRefresh()
  if (!preferenceRefreshMs.value) return
  refreshTimer.value = window.setInterval(() => {
    if (!batchState.value.running) loadData()
  }, preferenceRefreshMs.value)
}

function stopAutoRefresh() {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
    refreshTimer.value = null
  }
}

onMounted(async () => {
  try {
    const cur = await modelApi.getCurrent()
    currentModelVersion.value = cur?.version || cur?.model?.version || ''
  } catch (_) {
    /* 无当前版本时仅按缺 meta 判断过期 */
  }
  await applyUserPreferences()
  loadData()
  startAutoRefresh()
})

onBeforeUnmount(() => {
  stopAutoRefresh()
})
</script>

<style scoped>
.matches-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow-y: auto;
  padding: 4px;
}

.predict-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  flex-wrap: wrap;
}

.predict-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pred-tab {
  padding: 6px 14px;
  border-radius: 16px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
}

.pred-tab.active {
  background: rgba(var(--color-blue-rgb), 0.16);
  border-color: var(--color-blue);
  color: var(--color-blue);
  font-weight: 600;
}

.predict-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.batch-progress {
  font-size: 13px;
  color: var(--color-green);
}

.batch-progress.stale-hint {
  color: var(--color-orange);
}

.result-count {
  color: var(--color-gold);
  font-weight: 700;
}

.state-extra {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 4px;
}

.match-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

@media (max-width: 900px) {
  .match-grid {
    grid-template-columns: 1fr;
  }
}
</style>
