<template>
  <div v-if="loading" class="loading-state">
    <div class="loading-spinner"></div>
    <div class="loading-text">数据加载中...</div>
  </div>

  <div v-else-if="error" class="empty-state">
    <div class="empty-icon">⚠️</div>
    <div class="empty-text">数据加载失败</div>
    <div class="empty-hint">{{ error }}</div>
    <div class="error-actions">
      <button class="btn btn-primary" @click="loadData">重试</button>
      <button class="btn btn-primary" @click="goBack">返回列表</button>
    </div>
  </div>

  <div class="match-detail-page" v-else-if="match">
    <MatchDetailHeader
      :match="match"
      :home-team="getTeam(match.homeTeam)"
      :away-team="getTeam(match.awayTeam)"
      :league="getLeague(match.league)"
      :has-any-odds="hasAnyOdds"
      :has-nspf="hasNspf"
      :handicap-label="handicapLabel || ''"
      :odds-analysis-view="oddsAnalysisView"
      :heuristics-view="heuristicsView"
      :injury-alerts="injuryAlerts"
      :recalculating="recalculating"
      :loading="loading"
      :predict-error="predictError"
      @back="goBack"
      @recalculate="recalculatePrediction"
      @export="exportReport"
    />

    <PageTabs v-model="detailTab" :tabs="detailTabs" />

    <MatchDetailPrediction
      v-if="detailTab === 'prediction'"
      :match="match"
      :display-prediction="displayPrediction"
      :scenario-list="scenarioList"
      :primary-scenario-label="primaryScenarioLabel"
      :view-scenario-label="viewScenarioLabel"
      :scenario-reason-text="scenarioReasonText"
      :viewing-non-primary="viewingNonPrimary"
      :can-lock-viewed-scenario="canLockViewedScenario"
      :locking-scenario="lockingScenario"
      :view-scenario-id="viewScenarioId"
      :prediction-locked-fields="predictionLockedFields"
      :predict-error="predictError"
      :is-pred-locked="isPredLocked"
      @select-scenario="onSelectScenario"
      @lock-scenario="lockViewedScenario"
    />

    <MatchDetailModel
      v-if="detailTab === 'model'"
      ref="modelRef"
      :match="match"
      :chart-match="chartMatch"
      :home-short="getTeam(match.homeTeam).short"
      :away-short="getTeam(match.awayTeam).short"
      :has-xg-lambda="hasXgLambda"
      :primary-scenario-label="primaryScenarioLabel"
      :weight-used-list="weightUsedList"
      :is-pred-locked="isPredLocked"
      :weight-source-text="weightSourceText"
    />

    <template v-if="detailTab === 'data'">
      <MatchDetailHistory
        :match="match"
        :has-any-odds="hasAnyOdds"
        :handicap-label="handicapLabel || ''"
        :odds-snapshots="oddsSnapshots"
        :odds-snapshots-locked="oddsSnapshotsLocked"
        :head-to-head="headToHead"
      />
      <MatchDetailStats
        :visible="match.status === 'finished'"
        :sides="playerStatSides"
        :loading="playerStatsLoading"
        :crawling="crawlingPlayerStats"
        :error="playerStatsError"
        @crawl="crawlPlayerStats"
      />
    </template>
  </div>

  <div v-else class="empty-state">
    <div class="empty-icon">⚠️</div>
    <div class="empty-text">未找到该赛事</div>
    <div class="empty-hint">赛事ID: {{ route.params.id }}</div>
    <button class="btn btn-primary" @click="goBack">返回列表</button>
  </div>
</template>

<script setup>
/**
 * 赛事详情壳：路由参数、数据拉取编排、tab 切换与布局。
 * 各区块见 components/match/detail/*
 */
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { matchApi, predictionApi, scheduleApi } from '@/api'
import PageTabs from '@/components/common/PageTabs.vue'
import MatchDetailHeader from '@/components/match/detail/MatchDetailHeader.vue'
import MatchDetailPrediction from '@/components/match/detail/MatchDetailPrediction.vue'
import MatchDetailModel from '@/components/match/detail/MatchDetailModel.vue'
import MatchDetailHistory from '@/components/match/detail/MatchDetailHistory.vue'
import MatchDetailStats from '@/components/match/detail/MatchDetailStats.vue'
import { adaptTeam, adaptLeague } from '@/utils/adapters'
import { getActiveLeagues } from '@/utils/catalogCache'
import {
  formatHandicap,
  hasMatchOdds,
  hasNspfOdds,
  adaptOddsAnalysis,
  buildOddsAnalysisClient,
} from '@/utils/matchMeta'
import {
  convertKeys,
  formatDate,
  formatTime,
  normalizePrediction,
  normalizePlayerStats,
  xgCoverageText,
} from '@/components/match/detail/matchDetailFormat'
import { useMatchDetailScenarios } from '@/composables/useMatchDetailScenarios'

const route = useRoute()
const router = useRouter()

const detailTab = ref('prediction')
const detailTabs = [
  { key: 'prediction', label: '预测结论' },
  { key: 'model', label: '模型细节' },
  { key: 'data', label: '交锋与数据' },
]
const modelRef = ref(null)

const match = ref(null)
const teams = ref({})
const leagues = ref([])
const loading = ref(true)
const error = ref(null)
const recalculating = ref(false)
const predictError = ref('')
const playerStats = ref([])
const playerStatsLoading = ref(false)
const crawlingPlayerStats = ref(false)
const playerStatsError = ref('')
const headToHeadRaw = ref([])
const oddsSnapshots = ref([])
const oddsSnapshotsLocked = ref(false)
const matchAlerts = ref([])

const {
  viewScenarioId,
  lockingScenario,
  scenarioList,
  primaryScenarioLabel,
  viewScenarioLabel,
  scenarioReasonText,
  viewingNonPrimary,
  canLockViewedScenario,
  displayPrediction,
  chartMatch,
  predictionLockedFields,
  weightUsedList,
  hasXgLambda,
  syncViewScenarioFromPrediction,
  onSelectScenario,
  lockViewedScenario,
  isPredLocked,
  weightSourceText,
} = useMatchDetailScenarios(match, { predictError })

const headToHead = computed(() => {
  if (!match.value) return []
  const rows = headToHeadRaw.value || []
  if (!rows.length) return []
  return rows.map((h) => {
    const homeShort = getTeam(h.homeTeamId || h.home_team_id).short
    const awayShort = getTeam(h.awayTeamId || h.away_team_id).short
    return {
      matchId: h.matchId || h.match_id,
      date: formatDate(h.date),
      match: `${homeShort} vs ${awayShort}`,
      score: h.score || `${h.homeGoals ?? h.home_goals ?? 0}-${h.awayGoals ?? h.away_goals ?? 0}`,
      result: h.result || 'draw',
    }
  })
})

function getTeam(id) {
  const t = teams.value[id]
  if (!t) {
    return { id, name: id || '未知', short: id || '未知', logo: '⚪' }
  }
  const name = t.name || t.shortName || t.short || id || '未知'
  const short = t.short || t.shortName || name
  return {
    ...t,
    name,
    short,
    logo: t.logo || '⚪',
  }
}

function getLeague(id) {
  return leagues.value.find((l) => l.id === id) || { name: id || '未知联赛', icon: '⚽' }
}

const injuryAlerts = computed(() => {
  return (matchAlerts.value || []).filter((a) => {
    const t = String(a.type || a.alertType || '').toLowerCase()
    return t === 'injury' || t === '伤病影响'
  })
})

const hasAnyOdds = computed(() => hasMatchOdds(match.value))
const hasNspf = computed(() => hasNspfOdds(match.value))
const handicapLabel = computed(() => formatHandicap(match.value?.handicap))
const oddsAnalysisView = computed(() => {
  const m = match.value
  if (!m) return null
  let result = m.prediction?.hasPrediction || m.prediction?.homeWinProb != null
    ? buildOddsAnalysisClient(m, m.prediction)
    : m.oddsAnalysis
  const sourceHeuristics = m.oddsAnalysis?.heuristics
  if (result && sourceHeuristics && !result.heuristics) {
    return { ...result, heuristics: sourceHeuristics }
  }
  return result || null
})
const heuristicsView = computed(() => oddsAnalysisView.value?.heuristics || match.value?.oddsAnalysis?.heuristics || null)

const homePlayerStats = computed(() =>
  playerStats.value.filter((p) => p.isHome).sort((a, b) => (b.rating || 0) - (a.rating || 0))
)
const awayPlayerStats = computed(() =>
  playerStats.value.filter((p) => !p.isHome).sort((a, b) => (b.rating || 0) - (a.rating || 0))
)

const playerStatSides = computed(() => {
  if (!match.value) return []
  return [
    {
      key: 'home',
      label: '主队',
      teamName: getTeam(match.value.homeTeam).name,
      stats: homePlayerStats.value,
    },
    {
      key: 'away',
      label: '客队',
      teamName: getTeam(match.value.awayTeam).name,
      stats: awayPlayerStats.value,
    },
  ]
})

async function loadPlayerStats(matchId) {
  playerStatsLoading.value = true
  playerStatsError.value = ''
  try {
    const res = await matchApi.getPlayerStats(matchId)
    playerStats.value = normalizePlayerStats(res?.player_stats || res?.playerStats || [])
  } catch (err) {
    playerStats.value = []
    playerStatsError.value = err?.message || '球员统计加载失败'
  } finally {
    playerStatsLoading.value = false
  }
}

async function crawlPlayerStats() {
  if (!match.value || crawlingPlayerStats.value) return
  crawlingPlayerStats.value = true
  playerStatsError.value = ''
  try {
    await scheduleApi.runMatchPlayerStatsCrawl(match.value.id)
    await loadPlayerStats(match.value.id)
  } catch (err) {
    playerStatsError.value = err?.message || '采集失败'
  } finally {
    crawlingPlayerStats.value = false
  }
}

const RETURN_LISTS = new Set([
  '/jingcai-bf', '/jingcai-bf-history', '/jingcai/bf', '/jingcai/history',
  '/matches', '/matches/upcoming', '/matches/finished', '/finished-matches',
])

function goBack() {
  const from = typeof route.query.from === 'string' ? route.query.from : ''
  if (RETURN_LISTS.has(from)) {
    router.push(from)
    return
  }
  if (match.value?.status === 'finished') {
    router.push('/matches/finished')
  } else {
    router.push('/matches/upcoming')
  }
}

async function loadData() {
  loading.value = true
  error.value = null
  match.value = null
  headToHeadRaw.value = []

  try {
    const matchId = route.params.id

    const [matchData, leagueList] = await Promise.all([
      matchApi.getById(matchId),
      getActiveLeagues(),
    ])

    const teamMap = {}
    if (matchData.home_team) {
      const t = adaptTeam(matchData.home_team)
      teamMap[t.id] = t
    }
    if (matchData.away_team) {
      const t = adaptTeam(matchData.away_team)
      teamMap[t.id] = t
    }
    teams.value = teamMap
    leagues.value = leagueList
    if (matchData.league) {
      const lg = adaptLeague(matchData.league)
      if (!leagues.value.find((l) => l.id === lg.id)) {
        leagues.value = [...leagues.value, lg]
      }
    }

    const convertedMatch = {
      id: matchData.id,
      homeTeam: matchData.home_team_id,
      awayTeam: matchData.away_team_id,
      league: matchData.league_id,
      status: matchData.status,
      date: formatDate(matchData.match_date),
      time: formatTime(matchData.match_time),
      homeGoals: matchData.home_goals,
      awayGoals: matchData.away_goals,
      result: matchData.result,
      venue: matchData.venue || '',
      weather: matchData.weather || '',
      temperature: matchData.temperature || '',
      pitch: matchData.pitch_condition || '',
      stage: matchData.stage || '',
      groupName: matchData.group_name || '',
      round: matchData.round_name || '',
      roundName: matchData.round_name || '',
      handicap: matchData.handicap,
      oddsNspfWin: matchData.odds_nspf_win,
      oddsNspfDraw: matchData.odds_nspf_draw,
      oddsNspfLose: matchData.odds_nspf_lose,
      oddsSpfWin: matchData.odds_spf_win,
      oddsSpfDraw: matchData.odds_spf_draw,
      oddsSpfLose: matchData.odds_spf_lose,
      oddsAnalysis: adaptOddsAnalysis(matchData.odds_analysis || matchData.oddsAnalysis),
    }

    headToHeadRaw.value = (matchData.head_to_head || matchData.headToHead || []).map(convertKeys)
    matchAlerts.value = convertKeys(matchData.risk_alerts || matchData.riskAlerts || [])
    oddsSnapshots.value = []
    oddsSnapshotsLocked.value = false
    try {
      const snaps = await matchApi.getOddsSnapshots(matchId, 30)
      oddsSnapshots.value = convertKeys(snaps?.snapshots || snaps || [])
    } catch (e) {
      oddsSnapshotsLocked.value = e?.code === 'FEATURE_LOCKED'
      oddsSnapshots.value = []
    }

    let predictionData = null
    predictError.value = ''
    try {
      predictionData = await predictionApi.getByMatch(matchId)
    } catch (_) {
      predictionData = null
    }

    if (!predictionData || !predictionData.home_win_prob) {
      try {
        predictionData = await predictionApi.calculate(
          matchData.home_team_id,
          matchData.away_team_id,
          matchId
        )
        convertedMatch.prediction = normalizePrediction(predictionData)
        syncViewScenarioFromPrediction(convertedMatch.prediction)
        match.value = convertedMatch
      } catch (calcErr) {
        predictError.value = calcErr?.message || '预测计算失败'
        convertedMatch.prediction = normalizePrediction(null)
        match.value = convertedMatch
      }
    } else {
      convertedMatch.prediction = normalizePrediction(predictionData)
      syncViewScenarioFromPrediction(convertedMatch.prediction)
      match.value = convertedMatch
    }

    if (convertedMatch.status === 'finished') {
      await loadPlayerStats(matchId)
    } else {
      playerStats.value = []
    }
  } catch (err) {
    error.value = err?.message || '数据加载失败，请检查后端服务'
  } finally {
    loading.value = false
  }

  if (match.value && detailTab.value === 'model') {
    await nextTick()
    refreshCharts()
  }
}

function refreshCharts() {
  nextTick(() => {
    modelRef.value?.refreshCharts?.()
  })
}

watch(detailTab, (tab) => {
  if (tab === 'model') refreshCharts()
})

function handleResize() {
  modelRef.value?.handleResize?.()
}

function exportReport() {
  if (!match.value) return
  const m = match.value
  const home = getTeam(m.homeTeam).name
  const away = getTeam(m.awayTeam).name
  const content = `足球量化分析报告
========================================
赛事ID: ${m.id}
联赛: ${getLeague(m.league).name}
对阵: ${home} vs ${away}
时间: ${m.date} ${m.time}
场地: ${m.venue}
天气: ${m.weather} ${m.temperature}
草坪: ${m.pitch}

【概率分布】
  主队胜: ${(m.prediction.homeWinProb * 100).toFixed(1)}%
  平局:   ${(m.prediction.drawProb * 100).toFixed(1)}%
  客队胜: ${(m.prediction.awayWinProb * 100).toFixed(1)}%

【预期进球数 λ】
  ${home} (主): ${m.prediction.lambdaHome}
  ${away} (客): ${m.prediction.lambdaAway}
${m.prediction.xgHome != null ? `
【xG λ】覆盖 ${xgCoverageText(m.prediction.xgCoverage)}
  ${home} (主): ${m.prediction.xgHome}
  ${away} (客): ${m.prediction.xgAway}
` : ''}
【融合权重】
  版本: ${m.prediction.modelVersion || '-'}
  来源: ${weightSourceText(m.prediction.weightSource)}
  权重: ${weightUsedList.value.map((w) => `${w.label} ${w.pct}`).join(' / ') || '未记录'}

【预测结论】
  倾向: ${m.prediction.tendency}
  信心等级: ${m.prediction.confidence}
  风险等级: ${m.prediction.riskLevel}
  主线比分: ${m.prediction.mainScore}
  备选剧本: ${(m.prediction.altScores || []).join('、')}
  总进球预测: ${m.prediction.totalGoals}

【关键变量】
${(m.prediction.keyVariables || []).map((v) => '  - ' + v).join('\n')}

【简要分析】
${m.prediction.analysis}

========================================
报告生成时间: ${new Date().toLocaleString('zh-CN')}
`
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `match-report-${m.id}.txt`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function recalculatePrediction() {
  if (!match.value || recalculating.value) return
  recalculating.value = true
  predictError.value = ''
  try {
    const predictionData = await matchApi.getPrediction(match.value.id, true)
    match.value.prediction = normalizePrediction(predictionData)
    syncViewScenarioFromPrediction(match.value.prediction)
    refreshCharts()
  } catch (err) {
    predictError.value = err?.message || '重新计算失败'
  } finally {
    recalculating.value = false
  }
}

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  await loadData()
  startLivePoll()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  stopLivePoll()
  modelRef.value?.disposeCharts?.()
})

watch(() => route.params.id, async () => {
  stopLivePoll()
  await loadData()
  startLivePoll()
})

const livePollTimer = ref(null)

function startLivePoll() {
  stopLivePoll()
  if (match.value?.status !== 'live') return
  livePollTimer.value = window.setInterval(async () => {
    try {
      const matchId = route.params.id
      const matchData = await matchApi.getById(matchId)
      if (!match.value) return
      const next = convertKeys(matchData)
      match.value.homeGoals = next.homeGoals ?? next.home_goals ?? match.value.homeGoals
      match.value.awayGoals = next.awayGoals ?? next.away_goals ?? match.value.awayGoals
      match.value.status = next.status || match.value.status
      match.value.time = next.time || next.matchTime || match.value.time
      if (match.value.status !== 'live') stopLivePoll()
    } catch (_) {
      /* 轮询失败忽略 */
    }
  }, 60000)
}

function stopLivePoll() {
  if (livePollTimer.value) {
    clearInterval(livePollTimer.value)
    livePollTimer.value = null
  }
}
</script>

<style scoped>
.match-detail-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow-y: auto;
  padding: 4px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 16px;
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid var(--border-color);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  font-size: 14px;
  color: var(--text-secondary);
}

.error-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 20px;
  gap: 14px;
}

.empty-icon {
  font-size: 56px;
  opacity: 0.3;
}

.empty-text {
  font-size: 18px;
  color: var(--text-secondary);
  font-weight: 600;
}

.empty-hint {
  font-size: 13px;
  color: var(--text-muted);
  font-family: 'Consolas', monospace;
}
</style>
