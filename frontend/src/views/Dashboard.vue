<template>
  <div class="dashboard">
    <!-- 错误提示 -->
    <div v-if="errorMsg" class="error-banner card">
      <span class="error-icon">⚠️</span>
      <span class="error-text">{{ errorMsg }}</span>
    </div>
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state card">
      <span class="loading-spinner"></span>
      <span class="loading-text">数据加载中...</span>
    </div>
    <template v-else>
    <!-- 欢迎横幅 -->
    <section class="welcome-banner card">
      <div class="welcome-left">
        <h1 class="welcome-title">
          {{ greeting }}，{{ displayName }} 👋
        </h1>
        <p class="welcome-subtitle">
          欢迎使用足球量化分析系统，{{ isAdmin ? '今日共有' : '你关注的联赛今日共有' }}
          <span class="text-gold text-bold">{{ todayMatches.length }}</span>
          场焦点赛事；近期验证准确率约
          <span class="text-gold text-bold">{{ latestAccuracyDisplay }}</span>
          （仅供研究参考，不构成投注建议）。
        </p>
      </div>
      <div class="welcome-right">
        <div class="stat-card" v-for="stat in statCards" :key="stat.label">
          <span class="stat-card-icon" :style="{ color: stat.color }">{{ stat.icon }}</span>
          <div class="stat-card-info">
            <span class="stat-card-value" :style="{ color: stat.color }">{{ stat.value }}</span>
            <span class="stat-card-label">{{ stat.label }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 视图切换（仅非 admin） -->
    <PageTabs
      v-if="!isAdmin"
      :tabs="[{ key: 'overview', label: '总览' }, { key: 'followed', label: '我的关注' }]"
      v-model="dashTab"
    />

    <!-- 未关注空态（普通用户） -->
    <section v-if="showFollowEmpty" class="card empty-follow">
      <div class="empty-follow-icon">🏆</div>
      <h2 class="empty-follow-title">还没有关注联赛</h2>
      <p class="empty-follow-text">关注你关心的联赛后，首页将只展示这些联赛的赛事、积分榜和射手榜。</p>
      <button class="btn btn-primary" @click="goLeagues">去联赛列表关注</button>
    </section>

    <!-- 我的关注视图（非 admin） -->
    <template v-else-if="!isAdmin && dashTab === 'followed'">
      <StateBlock v-if="followedLoading" type="loading" text="关注数据加载中..." />
      <StateBlock
        v-else-if="followedError"
        type="error"
        :text="followedError"
        retry-text="重新加载"
        @retry="loadFollowedView(true)"
      />
      <StateBlock
        v-else-if="!followedGroups.length"
        type="empty"
        text="暂无关注联赛数据，可在联赛页关注后查看"
      />
      <section v-else class="league-groups">
        <article v-for="group in followedGroups" :key="group.id" class="card league-group">
          <header class="group-header">
            <div class="group-title">
              <MediaImg :src="group.logo" :fallback="group.icon || '🏆'" size="sm" :alt="group.name" />
              <div>
                <h2>
                  {{ group.name }}
                  <span v-if="!group.isActive" class="inactive-tag">已停用</span>
                </h2>
                <span class="text-muted">{{ group.upcoming.length }} 场未赛</span>
              </div>
            </div>
            <button class="link-btn" @click="toggleFollowedBoard(group.id)">
              {{ followedExpanded[group.id] ? '收起积分榜' : '积分榜 / 射手' }}
            </button>
          </header>
          <StateBlock v-if="!group.upcoming.length" type="empty" text="该联赛暂无未赛" />
          <div v-else class="match-grid">
            <UpcomingMatchCard
              v-for="match in group.upcoming"
              :key="match.id"
              :match="match"
              :league="resolveLeague(match, group)"
              :home-team="teamInfo(match.homeTeam, match)"
              :away-team="teamInfo(match.awayTeam, match)"
              :predicting="isPredicting(match.id)"
              :error-tip="predictError[match.id] || ''"
              @detail="goMatch"
              @predict="calculatePrediction"
            />
          </div>
          <div v-if="followedExpanded[group.id]" class="board-wrap">
            <div class="board-col">
              <h3 class="board-title">积分榜 {{ group.seasonLabel }}</h3>
              <table v-if="group.standings.length" class="data-table">
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>球队</th>
                    <th>场</th>
                    <th>积分</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in group.standings" :key="row.team">
                    <td>
                      <span class="rank-badge" :class="rankClass(row.rank)">{{ row.rank }}</span>
                    </td>
                    <td>{{ teamInfo(row.team).short }}</td>
                    <td>{{ row.played }}</td>
                    <td class="text-gold">{{ row.points }}</td>
                  </tr>
                </tbody>
              </table>
              <div v-else class="board-empty">暂无积分榜</div>
            </div>
            <div class="board-col">
              <h3 class="board-title">射手榜 Top 5</h3>
              <ul v-if="group.scorers.length" class="board-scorer-list">
                <li v-for="scorer in group.scorers" :key="scorer.rank + scorer.name">
                  <span class="board-scorer-rank" :class="rankClass(scorer.rank)">{{ scorer.rank || '-' }}</span>
                  <span class="board-scorer-name">{{ scorer.name }}</span>
                  <span class="board-scorer-team text-muted">{{ teamInfo(scorer.team).short }}</span>
                  <span class="text-gold">{{ scorer.goals }} 球</span>
                </li>
              </ul>
              <div v-else class="board-empty">暂无射手榜</div>
            </div>
          </div>
        </article>
      </section>
    </template>

    <!-- 总览视图（admin 恒为总览） -->
    <template v-else>
    <!-- 今日焦点赛事 -->
    <section class="section">
      <div class="section-header">
        <h2 class="section-title"><span class="section-bar"></span>今日焦点赛事</h2>
        <span class="section-sub text-muted">{{ todayDate }} · {{ todayMatches.length }} 场</span>
      </div>
      <div v-if="!todayMatches.length" class="card empty-follow">
        <p class="empty-follow-text">{{ isAdmin ? '今日暂无未赛' : '关注的联赛今日暂无未赛' }}</p>
      </div>
      <div v-else class="match-grid">
        <UpcomingMatchCard
          v-for="match in todayMatches"
          :key="match.id"
          :match="match"
          :league="resolveLeague(match)"
          :home-team="teamInfo(match.homeTeam, match)"
          :away-team="teamInfo(match.awayTeam, match)"
          :predicting="isPredicting(match.id)"
          :error-tip="predictError[match.id] || ''"
          @detail="goMatch"
          @predict="calculatePrediction"
        />
      </div>
    </section>

    <!-- 中间区域：准确率趋势 + 风险预警 -->
    <section v-if="!showFollowEmpty" class="section section-two-col">
      <!-- 模型准确率趋势 -->
      <div class="card chart-card">
        <div class="section-header">
          <h2 class="section-title"><span class="section-bar"></span>模型准确率趋势</h2>
          <span class="section-sub text-muted">近14天</span>
        </div>
        <div ref="chartRef" class="chart-container"></div>
      </div>

      <!-- 风险预警快览 -->
      <div v-if="canViewRisk" class="card risk-card">
        <div class="section-header">
          <h2 class="section-title"><span class="section-bar"></span>风险预警快览</h2>
          <span class="section-sub text-muted">{{ riskAlerts.length }} 条预警</span>
        </div>
        <ul class="risk-list">
          <li
            v-for="alert in topRiskAlerts"
            :key="alert.id"
            class="risk-item"
            @click="goMatch(alert.matchId)"
          >
            <div class="risk-item-top">
              <span class="risk-match">{{ alert.match }}</span>
              <span class="tag" :class="`tag-${alert.level}`">{{ levelText(alert.level) }}</span>
            </div>
            <div class="risk-item-type">
              <span class="text-muted text-sm">类型：{{ alert.type }}</span>
              <span class="text-muted text-sm">{{ alert.time }}</span>
            </div>
            <p class="risk-desc text-secondary">{{ alert.description }}</p>
          </li>
        </ul>
      </div>
    </section>

    <!-- 底部区域：积分榜 + 射手榜 -->
    <section v-if="!showFollowEmpty" class="section section-two-col">
      <!-- 积分榜 -->
      <div class="card table-card">
        <div class="section-header">
          <h2 class="section-title"><span class="section-bar"></span>{{ standingsLeagueName }}积分榜</h2>
          <span class="section-sub text-muted">{{ standingsSeasonLabel }}赛季</span>
        </div>
        <div v-if="standingsTabs.length > 1" class="league-tabs">
          <button
            v-for="tab in standingsTabs"
            :key="tab.id"
            type="button"
            class="league-tab"
            :class="{ active: standingsLeagueId === tab.id }"
            @click="switchStandingsLeague(tab.id)"
          >{{ tab.name }}</button>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th class="col-rank">排名</th>
              <th class="col-team">球队</th>
              <th>场次</th>
              <th>胜</th>
              <th>平</th>
              <th>负</th>
              <th>进球</th>
              <th>失球</th>
              <th>积分</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in standings" :key="row.team">
              <td class="col-rank">
                <span class="rank-badge" :class="rankClass(row.rank)">{{ row.rank }}</span>
              </td>
              <td class="col-team">
                <MediaImg :src="teamInfo(row.team).logo" fallback="⚽" img-class="team-logo-sm" size="xs" :alt="teamInfo(row.team).name" />
                <span>{{ teamInfo(row.team).short }}</span>
              </td>
              <td>{{ row.played }}</td>
              <td class="text-green">{{ row.won }}</td>
              <td>{{ row.drawn }}</td>
              <td class="text-red">{{ row.lost }}</td>
              <td>{{ row.gf }}</td>
              <td>{{ row.ga }}</td>
              <td class="col-points text-gold text-bold">{{ row.points }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 射手榜 -->
      <div class="card scorer-card">
        <div class="section-header">
          <h2 class="section-title"><span class="section-bar"></span>射手榜</h2>
          <span class="section-sub text-muted">Top 5</span>
        </div>
        <ul class="scorer-list">
          <li
            v-for="scorer in topScorers"
            :key="scorer.rank"
            class="scorer-item"
          >
            <span class="scorer-rank" :class="rankClass(scorer.rank)">{{ scorer.rank }}</span>
            <div class="scorer-info">
              <div class="scorer-name-row">
                <span class="scorer-name">{{ scorer.name }}</span>
                <span class="scorer-team text-muted text-sm">
                  {{ teamInfo(scorer.team).short }}
                </span>
              </div>
              <div class="scorer-stats">
                <span class="stat-block">
                  <span class="stat-num text-gold">{{ scorer.goals }}</span>
                  <span class="stat-label-sm text-muted">球</span>
                </span>
                <span class="stat-block">
                  <span class="stat-num text-blue">{{ scorer.assists }}</span>
                  <span class="stat-label-sm text-muted">助</span>
                </span>
              </div>
            </div>
            <div class="scorer-bar-wrap">
              <div
                class="scorer-bar"
                :style="{ width: scorerPercent(scorer.goals) + '%' }"
              ></div>
            </div>
          </li>
        </ul>
      </div>
    </section>
    </template>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import echarts from '@/utils/echarts'
import { CHART_COLORS } from '@/utils/chartTheme'
import {
  matchApi,
  trendApi,
  standingsApi,
  scorersApi,
  riskApi,
  scheduleApi,
  followApi,
} from '@/api'
import { useUserStore } from '@/stores/user'
import { useFollowsStore } from '@/stores/follows'
import { hasAnyPermission } from '@/utils/permissions'
import {
  adaptDashboardMatch,
  adaptStandings,
  adaptScorer,
  adaptRisk,
  adaptTrend,
  adaptPrediction,
  unwrapList,
} from '@/utils/adapters'
import { getTeamMap, getActiveLeagues } from '@/utils/catalogCache'
import PageTabs from '@/components/common/PageTabs.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import UpcomingMatchCard from '@/components/match/UpcomingMatchCard.vue'

const router = useRouter()
const userStore = useUserStore()
const followsStore = useFollowsStore()
const isAdmin = computed(() => userStore.isAdmin)
const canViewRisk = computed(() => hasAnyPermission('risk:manage'))
const showFollowEmpty = computed(() => !isAdmin.value && followsStore.loaded && !followsStore.ids.length)
const standingsLeagueId = ref('EPL')
const standingsTabs = ref([])
const summaryBoards = ref([])
const chartRef = ref(null)
let chartInstance = null

// ===== Tab / 关注视图状态 =====
const route = useRoute()
const dashTab = ref(route.query.tab === 'followed' ? 'followed' : 'overview')
const followedLoading = ref(false)
const followedError = ref('')
const followedGroups = ref([])
const followedLoaded = ref(false)
const followedExpanded = reactive({})

// ===== 单场预测（UpcomingMatchCard 按钮） =====
const predictingIds = reactive({})
const predictError = reactive({})

function isPredicting(matchId) {
  return !!predictingIds[matchId]
}

function findMatchById(matchId) {
  const today = todayMatches.value.find((m) => m.id === matchId)
  if (today) return { list: todayMatches.value, match: today }
  for (const group of followedGroups.value) {
    const hit = group.upcoming.find((m) => m.id === matchId)
    if (hit) return { list: group.upcoming, match: hit }
  }
  return null
}

async function calculatePrediction(match, recalculate = false) {
  if (predictingIds[match.id]) return
  predictingIds[match.id] = true
  delete predictError[match.id]
  try {
    const result = await matchApi.getPrediction(match.id, recalculate)
    const found = findMatchById(match.id)
    if (found) found.match.prediction = adaptPrediction(result)
  } catch (e) {
    predictError[match.id] = e?.message || '预测计算失败'
  } finally {
    delete predictingIds[match.id]
  }
}

// ===== 数据状态 =====
const loading = ref(true)
const errorMsg = ref('')
const todayMatches = ref([])
const accuracyTrend = ref([])
const standings = ref([])
const topScorers = ref([])
const riskAlerts = ref([])
const leagues = ref([])
const teams = ref({})
const standingsSeasonLabel = ref('当前')
const analysisCount = ref(0)
const activeSources = ref(0)

// 今日日期（动态计算）
const todayDate = computed(() => {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
})

const topRiskAlerts = computed(() => riskAlerts.value.slice(0, 2))

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '凌晨好'
  if (hour < 12) return '上午好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const displayName = computed(
  () => userStore.user?.username || userStore.user?.name || '数据分析员'
)

const standingsLeagueName = computed(() => {
  const tab = standingsTabs.value.find((t) => t.id === standingsLeagueId.value)
  if (tab?.name) return tab.name
  return leagueName(standingsLeagueId.value) || '联赛'
})

const statCards = computed(() => {
  const cards = [
    { label: '今日赛事', value: todayMatches.value.length, icon: '⚽', color: 'var(--color-gold)' },
    { label: '模型准确率', value: latestAccuracy() + '%', icon: '🎯', color: 'var(--color-green)' },
    { label: '累计分析次数', value: analysisCount.value || '-', icon: '📊', color: 'var(--color-blue)' },
  ]
  if (isAdmin.value) {
    cards.push({ label: '启用调度任务', value: activeSources.value || '-', icon: '🔗', color: 'var(--color-orange)' })
  } else {
    cards.push({ label: '关注联赛', value: followsStore.count || 0, icon: '🏆', color: 'var(--color-gold)' })
  }
  return cards
})

const latestAccuracyDisplay = computed(() => {
  const v = latestAccuracy()
  if (v == null || v === 0) return '暂无'
  return `${Number(v).toFixed(1)}%`
})

function latestAccuracy() {
  if (!accuracyTrend.value.length) return 0
  return accuracyTrend.value[accuracyTrend.value.length - 1].accuracy
}

function teamInfo(teamId, match) {
  if (match?.homeTeam === teamId && match.homeTeamInfo) return match.homeTeamInfo
  if (match?.awayTeam === teamId && match.awayTeamInfo) return match.awayTeamInfo
  return teams.value[teamId] || { short: teamId, logo: '⚽', name: teamId }
}

function leagueName(leagueId) {
  const item = leagues.value.find(l => l.id === leagueId)
  return item ? item.name : leagueId
}

function leagueIcon(leagueId) {
  const item = leagues.value.find(l => l.id === leagueId)
  return item ? item.icon : '🏆'
}

function leagueLogo(leagueId) {
  const item = leagues.value.find(l => l.id === leagueId)
  return item ? item.logo : ''
}

/** 为 UpcomingMatchCard 解析联赛对象（优先用赛事自带 leagueInfo，其次全局联赛表，最后关注组数据） */
function resolveLeague(match, group) {
  if (match?.leagueInfo?.name) return match.leagueInfo
  const item = leagues.value.find(l => l.id === match?.league)
  if (item) return item
  if (group) return { name: group.name, icon: group.icon, logo: group.logo }
  return { name: leagueName(match?.league), icon: leagueIcon(match?.league), logo: leagueLogo(match?.league) }
}

function levelText(level) {
  return { high: '高风险', mid: '中风险', low: '低风险' }[level] || level
}

function rankClass(rank) {
  if (rank === 1) return 'rank-gold'
  if (rank === 2) return 'rank-silver'
  if (rank === 3) return 'rank-bronze'
  return ''
}

function scorerPercent(goals) {
  const max = Math.max(...topScorers.value.map(s => s.goals), 1)
  return Math.round((goals / max) * 100)
}

function goMatch(id) {
  router.push(`/match/${id}`)
}

function goLeagues() {
  router.push('/leagues')
}

// ===== 我的关注视图 =====
function toggleFollowedBoard(leagueId) {
  followedExpanded[leagueId] = !followedExpanded[leagueId]
}

function followedSeasonLabel(raw) {
  if (!raw) return ''
  return String(raw).replace(/(\d{4})-(\d{4})/, (_, a, b) => `${a}-${String(b).slice(2)}`)
}

async function loadFollowedView(force = false) {
  if (isAdmin.value) return
  if (!force && followedLoaded.value) return
  followedLoading.value = true
  followedError.value = ''
  try {
    await followsStore.ensureLoaded()
    const [summary, teamMap] = await Promise.all([
      followApi.summary({
        per_league_matches: 5,
        match_limit: 40,
        standings_limit: 8,
        scorers_limit: 5,
        include_children: followsStore.includeChildren,
      }),
      getTeamMap().catch(() => new Map()),
    ])
    teamMap.forEach((t, id) => {
      if (!teams.value[id]) teams.value[id] = t
    })

    const matches = unwrapList(summary, 'matches').map(adaptDashboardMatch)
    matches.forEach((m) => {
      if (m.homeTeamInfo?.id) teams.value[m.homeTeamInfo.id] = m.homeTeamInfo
      if (m.awayTeamInfo?.id) teams.value[m.awayTeamInfo.id] = m.awayTeamInfo
    })
    const boards = summary?.boards || []
    const leagueList = summary?.leagues || followsStore.leagues
    followsStore.applyPayload(summary)

    const childMap = summary?.child_map || followsStore.childMap || {}
    const includeChildren = followsStore.includeChildren
    followedGroups.value = leagueList.map((league) => {
      const board = boards.find((b) => b.league_id === league.id) || {}
      const childIds = new Set(childMap[league.id] || league.child_ids || [])
      return {
        id: league.id,
        name: league.name,
        logo: league.logo,
        icon: league.icon,
        isActive: league.is_active !== false,
        seasonLabel: followedSeasonLabel(board.season),
        upcoming: matches.filter((m) => (
          m.league === league.id || (includeChildren && childIds.has(m.league))
        )),
        standings: (board.standings || []).map(adaptStandings),
        scorers: (board.scorers || []).slice(0, 5).map(adaptScorer),
      }
    })
    followedLoaded.value = true
  } catch (e) {
    followedError.value = e?.message || '关注数据加载失败'
    followedGroups.value = []
  } finally {
    followedLoading.value = false
  }
}

function applySummaryBoard(leagueId) {
  const board = summaryBoards.value.find((item) => item.league_id === leagueId)
  if (!board) return false
  standings.value = (board.standings || []).map(adaptStandings)
  topScorers.value = (board.scorers || []).slice(0, 5).map(adaptScorer)
  if (board.season) {
    standingsSeasonLabel.value = String(board.season).replace(/(\d{4})-(\d{4})/, (_, a, b) => `${a}-${String(b).slice(2)}`)
  }
  return true
}

async function switchStandingsLeague(leagueId) {
  if (!leagueId || standingsLeagueId.value === leagueId) return
  standingsLeagueId.value = leagueId
  if (!isAdmin.value && applySummaryBoard(leagueId)) return
  try {
    const [standingsData, scorersData] = await Promise.all([
      standingsApi.getByLeague(leagueId),
      scorersApi.getByLeague(leagueId),
    ])
    standings.value = unwrapList(standingsData, 'standings').map(adaptStandings)
    topScorers.value = unwrapList(scorersData, 'scorers').slice(0, 5).map(adaptScorer)
    const seasonRaw = standingsData?.standings?.[0]?.season || scorersData?.scorers?.[0]?.season
    if (seasonRaw) {
      standingsSeasonLabel.value = String(seasonRaw).replace(/(\d{4})-(\d{4})/, (_, a, b) => `${a}-${String(b).slice(2)}`)
    }
  } catch (e) {
    console.warn('切换积分榜失败:', e)
  }
}

// ===== 加载数据 =====
async function loadData() {
  loading.value = true
  errorMsg.value = ''
  try {
    analysisCount.value = Number(userStore.user?.total_analysis || 0)
    await followsStore.ensureLoaded()

    const [teamMapRaw, leagueList] = await Promise.all([
      getTeamMap(),
      getActiveLeagues(),
    ])
    const teamMap = {}
    teamMapRaw.forEach((t, id) => {
      teamMap[id] = t
    })
    teams.value = teamMap
    leagues.value = leagueList

    const followedIds = followsStore.ids
    const adminView = isAdmin.value
    if (!adminView && !followedIds.length) {
      todayMatches.value = []
      standings.value = []
      topScorers.value = []
      riskAlerts.value = []
      standingsTabs.value = []
      summaryBoards.value = []
      accuracyTrend.value = unwrapList(await trendApi.getRecent(30).catch(() => ({})), 'trends').map(adaptTrend)
      return
    }

    if (!adminView) {
      const [summary, trendData] = await Promise.all([
        followApi.summary({
          match_limit: 8,
          standings_limit: 8,
          scorers_limit: 5,
          include_children: followsStore.includeChildren,
        }),
        trendApi.getRecent(30),
      ])
      followsStore.applyPayload(summary)
      todayMatches.value = unwrapList(summary, 'matches').map(adaptDashboardMatch)
      todayMatches.value.forEach((m) => {
        if (m.homeTeamInfo?.id) teams.value[m.homeTeamInfo.id] = m.homeTeamInfo
        if (m.awayTeamInfo?.id) teams.value[m.awayTeamInfo.id] = m.awayTeamInfo
      })
      accuracyTrend.value = unwrapList(trendData, 'trends').map(adaptTrend)
      summaryBoards.value = summary?.boards || []
      standingsTabs.value = summaryBoards.value.map((board) => ({
        id: board.league_id,
        name: board.league_name || board.league_id,
      }))
      const primaryLeague = followedIds.includes('EPL') ? 'EPL' : (summary?.ids?.[0] || followedIds[0])
      standingsLeagueId.value = primaryLeague
      applySummaryBoard(primaryLeague)
      riskAlerts.value = canViewRisk.value
        ? unwrapList(summary, 'alerts').map(adaptRisk)
        : []
      return
    }

    const primaryLeague = 'EPL'
    standingsLeagueId.value = primaryLeague
    standingsTabs.value = []
    summaryBoards.value = []

    const [matchesData, trendData, standingsData, scorersData, riskData, crawlerStatus] = await Promise.all([
      matchApi.getUpcoming({ page_size: 8 }),
      trendApi.getRecent(30),
      standingsApi.getByLeague(primaryLeague),
      scorersApi.getByLeague(primaryLeague),
      canViewRisk.value ? riskApi.getAll().catch(() => ({ alerts: [] })) : Promise.resolve({ alerts: [] }),
      scheduleApi.getStatus().catch(() => null),
    ])

    todayMatches.value = unwrapList(matchesData, 'matches').map(adaptDashboardMatch)
    todayMatches.value.forEach((m) => {
      if (m.homeTeamInfo?.id) teams.value[m.homeTeamInfo.id] = m.homeTeamInfo
      if (m.awayTeamInfo?.id) teams.value[m.awayTeamInfo.id] = m.awayTeamInfo
    })
    accuracyTrend.value = unwrapList(trendData, 'trends').map(adaptTrend)
    standings.value = unwrapList(standingsData, 'standings').map(adaptStandings)
    topScorers.value = unwrapList(scorersData, 'scorers').slice(0, 5).map(adaptScorer)
    riskAlerts.value = unwrapList(riskData, 'alerts').map(adaptRisk)

    const tasks = crawlerStatus?.tasks || crawlerStatus?.schedules || []
    if (Array.isArray(tasks) && tasks.length) {
      activeSources.value = tasks.filter((t) => t.enabled || t.is_enabled || t.status === 'running').length
    } else if (crawlerStatus?.enabled_count != null) {
      activeSources.value = Number(crawlerStatus.enabled_count)
    } else {
      activeSources.value = Object.values(crawlerStatus || {}).filter(
        (v) => v && typeof v === 'object' && (v.enabled || v.is_enabled)
      ).length || '-'
    }

    const seasonRaw = standingsData?.standings?.[0]?.season || scorersData?.scorers?.[0]?.season
    if (seasonRaw) {
      standingsSeasonLabel.value = String(seasonRaw).replace(/(\d{4})-(\d{4})/, (_, a, b) => `${a}-${String(b).slice(2)}`)
    }
  } catch (e) {
    console.error('[Dashboard] 数据加载失败:', e)
    errorMsg.value = e?.message || '数据加载失败，请检查后端服务是否启动'
  } finally {
    loading.value = false
  }
  await nextTick()
  initChart()
}

function initChart() {
  if (!chartRef.value) return
  if (!accuracyTrend.value.length) return
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  chartInstance = echarts.init(chartRef.value)
  const dates = accuracyTrend.value.map(item => item.date)
  const values = accuracyTrend.value.map(item => item.accuracy)
  chartInstance.setOption({
    backgroundColor: 'transparent',
    grid: { top: 30, right: 20, bottom: 30, left: 45 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 31, 58, 0.95)',
      borderColor: CHART_COLORS.border,
      textStyle: { color: CHART_COLORS.textPrimary, fontSize: 12 },
      formatter: (params) => {
        const p = params[0]
        return `${p.axisValue}<br/>准确率：<span style="color:${CHART_COLORS.green};font-weight:700">${p.value}%</span>`
      }
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: CHART_COLORS.border } },
      axisLabel: { color: CHART_COLORS.textMuted, fontSize: 11 },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      min: 68,
      max: 76,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: CHART_COLORS.textMuted, fontSize: 11, formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(30, 58, 95, 0.5)', type: 'dashed' } }
    },
    series: [
      {
        name: '准确率',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        data: values,
        lineStyle: { color: CHART_COLORS.green, width: 2 },
        itemStyle: { color: CHART_COLORS.green, borderColor: CHART_COLORS.bgPrimary, borderWidth: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(61, 255, 154, 0.35)' },
            { offset: 1, color: 'rgba(61, 255, 154, 0.02)' }
          ])
        }
      }
    ]
  })
}

function handleResize() {
  chartInstance && chartInstance.resize()
}

// 关注联赛变化：刷新总览并使「我的关注」缓存失效
watch(
  () => `${followsStore.ids.join(',')}|${followsStore.includeChildren}`,
  () => {
    followedLoaded.value = false
    if (loading.value) return
    if (!isAdmin.value) loadData()
    if (!isAdmin.value && dashTab.value === 'followed') loadFollowedView(true)
  }
)

// 切到「我的关注」tab 时懒加载（仅首次）；切回总览时重建图表
watch(dashTab, async (tab) => {
  if (tab === 'followed' && !isAdmin.value) {
    loadFollowedView()
  } else if (tab === 'overview') {
    await nextTick()
    initChart()
    chartInstance && chartInstance.resize()
  }
})

onMounted(() => {
  loadData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})
</script>

<style scoped>
.dashboard {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  overflow-y: auto;
}

/* PageTabs 自带 margin-bottom，这里由容器 gap 控制间距 */
.dashboard :deep(.page-tabs) {
  margin-bottom: 0;
}

/* 错误提示 */
.error-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(var(--color-red-rgb), 0.1);
  border: 1px solid rgba(var(--color-red-rgb), 0.4);
  border-left: 3px solid var(--color-red);
  color: var(--color-red);
  font-size: 13px;
}

.error-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.error-text {
  line-height: 1.5;
}

/* 加载状态 */
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 80px 20px;
  color: var(--text-secondary);
  font-size: 14px;
}

.loading-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--border-color);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: dash-spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes dash-spin {
  to { transform: rotate(360deg); }
}

/* 欢迎横幅 */
.welcome-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-secondary) 100%);
  border: 1px solid var(--border-color);
}

.welcome-left {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.welcome-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.welcome-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
}

.welcome-right {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 12px;
  flex: 1;
  max-width: 720px;
}

.stat-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: var(--transition);
}

.stat-card:hover {
  border-color: rgba(var(--color-blue-rgb), 0.4);
  transform: translateY(-2px);
}

.stat-card-icon {
  font-size: 24px;
}

.stat-card-info {
  display: flex;
  flex-direction: column;
}

.stat-card-value {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
}

.stat-card-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.empty-follow {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 56px 24px;
  text-align: center;
}

.empty-follow-icon {
  font-size: 36px;
}

.empty-follow-title {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.empty-follow-text {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 420px;
}

.league-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 16px 12px;
}

.league-tab {
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}

.league-tab.active {
  border-color: var(--color-gold);
  color: var(--color-gold);
  background: rgba(212, 175, 55, 0.12);
}

/* 区块通用 */
.section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
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

/* 赛事卡片网格（UpcomingMatchCard 自带卡片样式） */
.match-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

/* 我的关注：按联赛分组 */
.league-groups {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.league-group {
  padding: var(--space-md) var(--space-lg) var(--space-lg);
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.group-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.group-title h2 {
  margin: 0;
  font-size: var(--font-lg);
  color: var(--text-primary);
}

.inactive-tag {
  margin-left: var(--space-sm);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
}

.link-btn {
  background: none;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}

.link-btn:hover {
  border-color: var(--color-blue);
  color: var(--color-blue);
}

/* 我的关注：积分榜 / 射手榜展开区 */
.board-wrap {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: var(--space-md);
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: 1px solid var(--border-color);
}

.board-title {
  margin: 0 0 var(--space-sm);
  font-size: 13px;
  color: var(--text-secondary);
}

.board-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: var(--space-sm) 0;
}

.board-scorer-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.board-scorer-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.board-scorer-rank {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.board-scorer-name {
  flex: 1;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.board-scorer-team {
  font-size: 12px;
}

@media (max-width: 800px) {
  .board-wrap {
    grid-template-columns: 1fr;
  }
}

/* 图表 */
.chart-card {
  display: flex;
  flex-direction: column;
}

.chart-container {
  width: 100%;
  height: 280px;
}

/* 风险预警 */
.risk-card {
  display: flex;
  flex-direction: column;
}

.risk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.risk-item {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-left: 3px solid var(--color-red);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  cursor: pointer;
  transition: var(--transition);
}

.risk-item:hover {
  background: var(--bg-hover);
  border-left-color: var(--color-orange);
}

.risk-item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.risk-match {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.risk-item-type {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.risk-desc {
  font-size: 12px;
  line-height: 1.5;
}

/* 表格 */
.table-card {
  display: flex;
  flex-direction: column;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table thead th {
  text-align: center;
  color: var(--text-muted);
  font-weight: 600;
  padding: 10px 6px;
  border-bottom: 1px solid var(--border-color);
  font-size: 12px;
}

.data-table thead th.col-team {
  text-align: left;
}

.data-table tbody td {
  text-align: center;
  padding: 10px 6px;
  border-bottom: 1px solid rgba(30, 58, 95, 0.4);
  color: var(--text-secondary);
  transition: var(--transition);
}

.data-table tbody td.col-team {
  text-align: left;
  color: var(--text-primary);
  font-weight: 600;
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

.col-rank {
  width: 50px;
}

.col-points {
  font-size: 15px;
}

.rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.rank-gold {
  background: linear-gradient(135deg, #ffd700, #ff9f43);
  color: #0a1628;
}

.rank-silver {
  background: linear-gradient(135deg, #c0c8d4);
  color: #0a1628;
}

.rank-bronze {
  background: linear-gradient(135deg, #cd7f32, #8a4b1a);
  color: #fff;
}

.team-logo-sm {
  margin-right: 6px;
  font-size: 14px;
}

/* 射手榜 */
.scorer-card {
  display: flex;
  flex-direction: column;
}

.scorer-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.scorer-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  transition: var(--transition);
  position: relative;
}

.scorer-item:hover {
  background: var(--bg-hover);
  border-color: rgba(var(--color-blue-rgb), 0.3);
}

.scorer-rank {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.scorer-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.scorer-name-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.scorer-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.scorer-stats {
  display: flex;
  gap: 16px;
}

.stat-block {
  display: flex;
  align-items: baseline;
  gap: 3px;
}

.stat-num {
  font-size: 14px;
  font-weight: 700;
}

.stat-label-sm {
  font-size: 11px;
}

.scorer-bar-wrap {
  width: 80px;
  height: 4px;
  background: var(--bg-secondary);
  border-radius: 2px;
  overflow: hidden;
  flex-shrink: 0;
}

.scorer-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--color-gold), var(--color-orange));
  border-radius: 2px;
  transition: width 0.6s ease;
}
</style>
