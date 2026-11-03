<template>
  <div class="model-quality-tab">
    <div class="card quality-card">
      <div class="card-header">
        <h2 class="card-title">数据质量看板</h2>
        <div class="card-actions">
          <span class="card-sub" v-if="qualityData?.generated_at">更新 {{ qualityData.generated_at }}</span>
          <button class="refresh-btn" @click="fetchQuality" :disabled="qualityLoading">
            {{ qualityLoading ? '加载中...' : '刷新' }}
          </button>
          <button
            class="btn btn-primary"
            @click="runP0AndRefresh"
            :disabled="p0Pipeline.running || envBackfill.running || trainOnly.running"
            title="射门历史补采 → 环境补全 → 全量训练（后台执行，可轮询进度）"
          >
            {{ p0Pipeline.running ? (p0PhaseLabel || 'P0 执行中...') : '执行 P0 补齐+训练' }}
          </button>
          <button
            class="btn btn-outline"
            @click="runTrainOnly"
            :disabled="trainOnly.running || p0Pipeline.running || isTraining"
            title="仅全量 train_all，不重跑采集（训练滞后时优先）"
          >
            {{ trainOnly.running || isTraining ? '训练中...' : '仅重训' }}
          </button>
          <button
            class="btn btn-outline"
            @click="runUelCatchup"
            :disabled="uelCatchup.running || p0Pipeline.running || extendedCatchup.running"
            title="欧联杯：富化赛程 → 射门补采 → 全量训练（默认入队）"
          >
            {{ uelCatchup.running ? 'UEL 补齐中...' : 'UEL 补齐+训练' }}
          </button>
          <button
            class="btn btn-outline"
            @click="runExtendedCatchup"
            :disabled="extendedCatchup.running || p0Pipeline.running || uelCatchup.running"
            title="P2/P3：MLS·BRA·SWE·FIN + NOR·K1 富化与射门补采（默认不训练）"
          >
            {{ extendedCatchup.running ? '扩展补齐中...' : '扩展联赛补齐' }}
          </button>
          <button
            class="btn btn-outline"
            @click="runEnvBackfill(false)"
            :disabled="envBackfill.running || p0Pipeline.running"
            title="Open-Meteo 补全天气/草坪（完赛优先有球场名，默认 1000 场）"
          >
            {{ envBackfill.running && !envBackfill.finishedOnly ? '环境补全中...' : '补全环境字段' }}
          </button>
          <button
            class="btn btn-outline"
            @click="runEnvBackfill(true)"
            :disabled="envBackfill.running || p0Pipeline.running"
            title="只补完赛且缺天气/草坪的场次"
          >
            {{ envBackfill.running && envBackfill.finishedOnly ? '完赛补全中...' : '仅完赛环境' }}
          </button>
          <button
            class="btn btn-outline"
            @click="runInjuryCrawl"
            :disabled="injuryCrawl.running || p0Pipeline.running"
            title="ESPN 伤病 → 临场 injury 预警（重点联赛）"
          >
            {{ injuryCrawl.running ? '伤病拉取中...' : '拉取伤病' }}
          </button>
          <button
            class="btn btn-outline"
            @click="toggleMappingGaps"
            :disabled="gapsLoading"
          >
            {{ gapsLoading ? '缺口加载中...' : (showGaps ? '收起映射缺口' : '查看映射缺口') }}
          </button>
        </div>
      </div>

      <div v-if="qualityError" class="quality-error">{{ qualityError }}</div>

      <div v-if="qualityData" class="quality-body">
        <div class="quality-kpis">
          <div class="qk">
            <span class="qk-label">射门统计覆盖</span>
            <b>{{ qualityData.totals?.player_stats_coverage_pct ?? '-' }}%</b>
            <span class="qk-sub">{{ qualityData.totals?.matches_with_player_stats }}/{{ qualityData.totals?.finished_matches }} 场</span>
          </div>
          <div class="qk">
            <span class="qk-label">完赛环境覆盖</span>
            <b>{{ qualityData.totals?.env_finished_pct ?? '-' }}%</b>
            <span class="qk-sub">未赛 {{ qualityData.totals?.env_upcoming_pct ?? 0 }}%</span>
          </div>
          <div class="qk" :class="{ warn: qualityData.training_lag?.is_stale }">
            <span class="qk-label">训练滞后</span>
            <b>{{ qualityData.training_lag?.is_stale ? '需重训' : '较新' }}</b>
            <span class="qk-sub">
              样本差 {{ qualityData.training_lag?.sample_gap ?? '-' }}
              · 落后 {{ qualityData.training_lag?.days_behind ?? '-' }} 天
            </span>
          </div>
          <div class="qk" :class="{ warn: !qualityData.model?.weights_has_hyperparams }">
            <span class="qk-label">超参落库</span>
            <b>{{ qualityData.model?.weights_has_hyperparams ? '已写入' : '缺失' }}</b>
            <span class="qk-sub">{{ qualityData.model?.version || '无 current' }}</span>
          </div>
          <div class="qk">
            <span class="qk-label">预测含场景</span>
            <b>{{ qualityData.totals?.predictions_with_scenarios ?? '-' }}</b>
            <span class="qk-sub">meta {{ qualityData.totals?.predictions_with_meta }}/{{ qualityData.totals?.predictions }}</span>
          </div>
          <div class="qk">
            <span class="qk-label">xG 非默认球队</span>
            <b>{{ qualityData.totals?.xg_teams_non_default ?? '-' }}</b>
            <span class="qk-sub">非默认 xg_for/against</span>
          </div>
          <div class="qk" :class="{ warn: slaMissCount > 0 }" v-if="qualityData.sla?.enabled !== false">
            <span class="qk-label">SLA 未达标</span>
            <b>{{ slaMissCount }}</b>
            <span class="qk-sub">配额 {{ qualityData.sla?.budget || qualityData.sla?.budget_per_run || '-' }}/次</span>
          </div>
          <div class="qk" :class="{ warn: (qualityData.quality_alerts || []).length }">
            <span class="qk-label">质量告警</span>
            <b>{{ (qualityData.quality_alerts || []).length }}</b>
            <span class="qk-sub">未处理 data_abnormal</span>
          </div>
        </div>

        <div class="quality-alerts" v-if="qualityData.quality_alerts?.length">
          <div class="qa-item" v-for="a in qualityData.quality_alerts" :key="a.id || a.match_name">
            <span class="tag" :class="a.level === 'high' ? 'tag-high' : 'tag-info'">{{ a.level }}</span>
            <span class="qa-title">{{ a.description }}</span>
            <span class="qa-action">{{ a.recommended_action }}</span>
          </div>
        </div>

        <div class="quality-actions" v-if="qualityData.actions?.length">
          <div class="qa-item" v-for="(a, i) in qualityData.actions" :key="i">
            <span class="tag" :class="a.priority === 'high' ? 'tag-high' : 'tag-info'">{{ a.priority }}</span>
            <span class="qa-title">{{ a.title }}</span>
            <span class="qa-action">{{ a.action }}</span>
            <button
              v-if="a.cta"
              type="button"
              class="btn btn-outline qa-cta"
              :disabled="p0Pipeline.running || envBackfill.running || trainOnly.running || injuryCrawl.running || recalcState.running"
              @click="runQualityCta(a.cta)"
            >
              {{ qualityCtaLabel(a.cta) }}
            </button>
          </div>
        </div>

        <div class="table-wrapper quality-league-table">
          <p v-if="qualityLeagueLoading && !qualityData.by_league?.length" class="empty-hint">分联赛明细加载中…</p>
          <VirtualTable
            v-else-if="qualityData.by_league?.length"
            :items="qualityData.by_league"
            row-key="league_id"
            :height="360"
            class="compact"
          >
            <template #head>
              <tr>
                <th>联赛</th>
                <th>完赛</th>
                <th>有统计</th>
                <th>覆盖率</th>
                <th>SLA</th>
                <th>配额</th>
                <th>可补缺场</th>
                <th>无源缺场</th>
                <th>环境覆盖</th>
              </tr>
            </template>
            <template #row="{ row }">
              <td>{{ leagueName(row.league_id) }}</td>
              <td>{{ row.finished }}</td>
              <td>{{ row.with_player_stats }}</td>
              <td>{{ row.stats_coverage_pct }}%</td>
              <td :class="{ 'sla-miss': row.sla_met === false }">
                <template v-if="row.sla_target_pct != null">
                  {{ row.sla_coverage_pct }}% / {{ row.sla_target_pct }}%
                  <small v-if="row.sla_met === false">未达标</small>
                </template>
                <template v-else>-</template>
              </td>
              <td>{{ row.sla_limit ?? '-' }}</td>
              <td>{{ row.crawlable_missing }}</td>
              <td>{{ row.no_source_missing }}</td>
              <td>{{ row.env_coverage_pct }}%</td>
            </template>
          </VirtualTable>
        </div>
      </div>

      <p v-if="p0Pipeline.message" class="recalc-result" :class="{ error: p0Pipeline.error }">{{ p0Pipeline.message }}</p>
      <p v-if="trainOnly.message" class="recalc-result" :class="{ error: trainOnly.error }">{{ trainOnly.message }}</p>
      <p v-if="injuryCrawl.message" class="recalc-result" :class="{ error: injuryCrawl.error }">{{ injuryCrawl.message }}</p>
      <p v-if="uelCatchup.message" class="recalc-result" :class="{ error: uelCatchup.error }">{{ uelCatchup.message }}</p>
      <p v-if="extendedCatchup.message" class="recalc-result" :class="{ error: extendedCatchup.error }">{{ extendedCatchup.message }}</p>
      <p v-if="envBackfill.message" class="recalc-result" :class="{ error: envBackfill.error }">{{ envBackfill.message }}</p>

      <div v-if="showGaps && mappingGaps" class="gaps-panel">
        <div class="gaps-summary">
          缺统计合计 {{ mappingGaps.summary?.total_missing }}
          · 无源 {{ mappingGaps.summary?.no_source }}
          · 映射难 {{ mappingGaps.summary?.mapping_gap }}
          · 待补采 {{ mappingGaps.summary?.pending_crawl }}
        </div>
        <div class="gaps-notes">
          <p v-for="(n, i) in mappingGaps.notes || []" :key="i">{{ n }}</p>
        </div>

        <div class="gaps-filters">
          <div class="filter-item">
            <label>联赛</label>
            <select v-model="gapFilters.league_id" @change="onGapFilterChange">
              <option value="">全部联赛</option>
              <option v-for="opt in gapLeagueOptions" :key="opt.id" :value="opt.id">
                {{ opt.label }}（{{ opt.count }}）
              </option>
            </select>
          </div>
          <div class="filter-item">
            <label>原因</label>
            <select v-model="gapFilters.reason" @change="onGapFilterChange">
              <option value="">全部</option>
              <option value="no_source">无源</option>
              <option value="mapping_gap">映射难</option>
              <option value="pending_crawl">待补采</option>
            </select>
          </div>
          <button class="btn btn-sm" @click="fetchMappingGapsRows(gapPagination.page)" :disabled="gapsRowsLoading">
            {{ gapsRowsLoading ? '加载中…' : '刷新明细' }}
          </button>
        </div>

        <p v-if="gapsRowsLoading && !gapRows.length" class="empty-hint">缺口明细加载中…</p>
        <div class="table-wrapper" v-else-if="gapRows.length">
          <VirtualTable
            :items="gapRows"
            row-key="match_id"
            :height="400"
            class="compact"
          >
            <template #head>
              <tr>
                <th>联赛</th>
                <th>日期</th>
                <th>对阵</th>
                <th>阶段</th>
                <th>原因</th>
                <th>映射分</th>
              </tr>
            </template>
            <template #row="{ row: g }">
              <td>{{ leagueName(g.league_id) }}</td>
              <td>{{ g.match_date || '-' }}</td>
              <td>{{ g.home_name || g.home_team_id }} vs {{ g.away_name || g.away_team_id }}</td>
              <td>{{ g.stage || g.round_name || '-' }}</td>
              <td>{{ gapReasonText(g.reason) }}</td>
              <td>{{ g.home_map_score }}+{{ g.away_map_score }}</td>
            </template>
          </VirtualTable>
        </div>
        <p v-else-if="!gapsRowsLoading" class="empty-hint">当前筛选下暂无缺口场次</p>

        <Pagination
          class="gaps-pagination"
          :page="gapPagination.page"
          :page-size="gapPagination.page_size"
          :total="gapPagination.total"
          @change="changeGapPage"
        />

        <div class="weak-teams" v-if="mappingGaps.weak_teams?.length">
          <h4 class="detail-section-title">难映射球队（点击填写别名并确认）</h4>
          <div class="weak-tags">
            <button
              type="button"
              class="weak-tag"
              :class="{ active: aliasDraft.team_id === t.team_id }"
              v-for="t in mappingGaps.weak_teams.slice(0, 40)"
              :key="t.team_id"
              @click="selectWeakTeam(t)"
            >
              {{ t.name || t.team_id }} <small>{{ t.league_id }} · {{ t.map_score }}</small>
            </button>
          </div>
          <div class="alias-form" v-if="aliasDraft.team_id">
            <div class="filter-item">
              <label>别名</label>
              <input v-model="aliasDraft.alias" type="text" maxlength="120" />
            </div>
            <div class="filter-item">
              <label>球队 ID</label>
              <input v-model="aliasDraft.team_id" type="text" maxlength="20" />
            </div>
            <div class="filter-item">
              <label>ESPN 缩写</label>
              <input v-model="aliasDraft.espn_abbr" type="text" maxlength="20" placeholder="可选" />
            </div>
            <button class="btn btn-sm btn-primary" :disabled="aliasSaving" @click="saveTeamAlias">
              {{ aliasSaving ? '保存中...' : '确认写入' }}
            </button>
          </div>
        </div>

        <div class="pending-aliases">
          <div class="gaps-summary">
            待确认别名 {{ pendingAliases.length }}
            <button class="btn btn-sm" :disabled="aliasSaving" @click="suggestTeamAliases">从缺口生成</button>
            <button class="btn btn-sm" :disabled="aliasSaving" @click="fetchPendingAliases">刷新</button>
          </div>
          <div class="table-wrapper" v-if="pendingAliases.length">
            <table class="data-table compact">
              <thead>
                <tr>
                  <th>别名</th>
                  <th>球队</th>
                  <th>联赛</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in pendingAliases" :key="row.id">
                  <td>{{ row.alias }}</td>
                  <td>{{ row.team_id }}</td>
                  <td>{{ row.league_id || '-' }}</td>
                  <td>
                    <button class="btn btn-sm" :disabled="aliasSaving" @click="confirmPendingAlias(row)">确认</button>
                    <button class="btn btn-sm" :disabled="aliasSaving" @click="rejectPendingAlias(row)">忽略</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { scheduleApi } from '@/api'
import VirtualTable from '@/components/data/VirtualTable.vue'
import Pagination from '@/components/common/Pagination.vue'
import { leagueName } from './modelFormatters'
import {
  qualityData,
  p0Pipeline,
  p0PhaseLabel,
  runP0Pipeline,
  attachRunningP0,
  isTraining,
  startTraining,
  recalcState,
  recalculateUpcoming,
  dataEpoch,
  onTrainingDone,
} from './modelStore'

const router = useRouter()

const qualityLoading = ref(false)
const qualityLeagueLoading = ref(false)
const qualityError = ref(null)
const mappingGaps = ref(null)
const gapRows = ref([])
const gapPagination = ref({ page: 1, page_size: 20, total: 0, pages: 0 })
const gapFilters = reactive({ league_id: '', reason: '' })
const gapsLoading = ref(false)
const gapsRowsLoading = ref(false)
const showGaps = ref(false)
const envBackfill = ref({ running: false, message: '', error: false, finishedOnly: false })
const trainOnly = ref({ running: false, message: '', error: false })
const injuryCrawl = ref({ running: false, message: '', error: false })
const aliasDraft = ref({ alias: '', team_id: '', espn_abbr: '', league_id: '' })
const aliasSaving = ref(false)
const pendingAliases = ref([])
const uelCatchup = ref({ running: false, message: '', error: false, jobId: '' })
let uelPollInterval = null
const extendedCatchup = ref({ running: false, message: '', error: false, jobId: '' })
let extendedPollInterval = null

const GAP_REASON_LABELS = {
  no_source: '无源',
  mapping_gap: '映射难',
  pending_crawl: '待补采',
}

function gapReasonText(reason) {
  return GAP_REASON_LABELS[reason] || reason || '-'
}

const slaMissCount = computed(() =>
  (qualityData.value?.by_league || []).filter((r) => r.sla_met === false).length
)

const gapLeagueOptions = computed(() => {
  const stats = mappingGaps.value?.league_stats || []
  return stats
    .filter((s) => s.total_missing > 0)
    .sort((a, b) => b.total_missing - a.total_missing)
    .map((s) => ({ id: s.league_id, label: leagueName(s.league_id), count: s.total_missing }))
})

function mergeQualityActions(baseActions, byLeague) {
  const actions = [...(baseActions || [])]
  const crawlable = (byLeague || []).reduce((s, x) => s + (Number(x.crawlable_missing) || 0), 0)
  const hasCrawlable = actions.some((a) => a.title?.includes('可补射门统计'))
  if (crawlable >= 50 && !hasCrawlable) {
    actions.push({
      priority: 'mid',
      title: `约 ${crawlable} 场可补射门统计`,
      action: '执行 P0，或 POST /crawler/matches/player-stats/backfill?prefer_older=true',
    })
  }
  for (const row of (byLeague || []).filter((r) => r.sla_met === false).slice(0, 3)) {
    const title = `${row.league_id} 可补覆盖 ${row.sla_coverage_pct}% 低于 SLA ${row.sla_target_pct}%`
    if (!actions.some((a) => a.title === title)) {
      actions.push({
        priority: 'mid',
        title,
        action: `下次配额约 ${row.sla_limit ?? '-'} 场；执行 P0 或 backfill`,
      })
    }
  }
  return actions
}

async function fetchQualityByLeague() {
  qualityLeagueLoading.value = true
  try {
    const res = await scheduleApi.getDataQualityByLeague()
    const rows = res?.by_league || []
    if (qualityData.value) {
      qualityData.value.by_league = rows
      if (res?.sla) {
        qualityData.value.sla = { ...(qualityData.value.sla || {}), ...res.sla }
      }
      qualityData.value.actions = mergeQualityActions(
        qualityData.value.actions || [],
        rows,
      )
    }
  } catch (e) {
    qualityError.value = e?.message || '分联赛数据加载失败'
  } finally {
    qualityLeagueLoading.value = false
  }
}

async function fetchQuality() {
  qualityLoading.value = true
  qualityError.value = null
  try {
    const summary = await scheduleApi.getDataQualitySummary()
    qualityData.value = { ...summary, by_league: [] }
    qualityLoading.value = false
    await fetchQualityByLeague()
  } catch (e) {
    qualityError.value = e?.message || '数据质量看板加载失败'
    qualityLoading.value = false
  }
}

async function fetchMappingGapsRows(page = gapPagination.value.page) {
  gapsRowsLoading.value = true
  try {
    const res = await scheduleApi.getMappingGapsRows({
      page,
      page_size: gapPagination.value.page_size,
      league_id: gapFilters.league_id || undefined,
      reason: gapFilters.reason || undefined,
    })
    gapRows.value = res?.rows || []
    gapPagination.value = {
      ...gapPagination.value,
      ...(res?.pagination || {}),
    }
  } catch (e) {
    qualityError.value = e?.message || '映射缺口明细加载失败'
  } finally {
    gapsRowsLoading.value = false
  }
}

function changeGapPage(page) {
  if (page < 1 || page > gapPagination.value.pages) return
  gapPagination.value.page = page
  fetchMappingGapsRows(page)
}

function onGapFilterChange() {
  gapPagination.value.page = 1
  fetchMappingGapsRows(1)
}

async function toggleMappingGaps() {
  if (showGaps.value) {
    showGaps.value = false
    return
  }
  gapsLoading.value = true
  qualityError.value = null
  try {
    mappingGaps.value = await scheduleApi.getMappingGapsSummary()
    gapFilters.league_id = ''
    gapFilters.reason = ''
    gapPagination.value = { page: 1, page_size: 20, total: 0, pages: 0 }
    showGaps.value = true
    gapsLoading.value = false
    await Promise.all([fetchMappingGapsRows(1), fetchPendingAliases()])
  } catch (e) {
    qualityError.value = e?.message || '映射缺口加载失败'
    gapsLoading.value = false
  }
}

async function runEnvBackfill(finishedOnly = false) {
  envBackfill.value = { running: true, message: '', error: false, finishedOnly: !!finishedOnly }
  try {
    const res = await scheduleApi.backfillEnvironment({
      limit: 1000,
      only_missing: true,
      finished_only: !!finishedOnly,
    })
    const cov = res?.coverage || {}
    envBackfill.value.message = (
      `环境补全${finishedOnly ? '（仅完赛）' : ''}：扫描 ${res?.scanned ?? 0} · 更新 ${res?.updated ?? 0}`
      + (cov.env_finished_pct != null ? ` · 完赛环境覆盖 ${cov.env_finished_pct}%` : '')
      + (cov.env_upcoming_pct != null ? ` · 未赛 ${cov.env_upcoming_pct}%` : '')
    )
    await fetchQuality()
  } catch (e) {
    envBackfill.value.error = true
    envBackfill.value.message = e?.message || '环境补全失败'
  } finally {
    envBackfill.value.running = false
  }
}

async function runTrainOnly() {
  if (trainOnly.value.running || isTraining.value || p0Pipeline.value.running) return
  trainOnly.value = { running: true, message: '正在启动全量训练...', error: false }
  try {
    await startTraining()
    trainOnly.value.message = '训练已启动，进度见「训练记录 / 概览」'
    trainOnly.value.error = false
  } catch (e) {
    trainOnly.value.error = true
    trainOnly.value.message = e?.message || '启动训练失败'
  } finally {
    trainOnly.value.running = false
  }
}

async function runInjuryCrawl() {
  if (injuryCrawl.value.running || p0Pipeline.value.running) return
  injuryCrawl.value = { running: true, message: '正在拉取 ESPN 伤病...', error: false }
  try {
    const res = await scheduleApi.runInjuryCrawl()
    const n = res?.alerts_upserted ?? res?.created ?? res?.injury_rows ?? 0
    injuryCrawl.value.message = res?.message || `伤病采集完成：写入/更新预警约 ${n} 条`
    injuryCrawl.value.error = false
  } catch (e) {
    injuryCrawl.value.error = true
    injuryCrawl.value.message = e?.message || '伤病采集失败'
  } finally {
    injuryCrawl.value.running = false
  }
}

function qualityCtaLabel(cta) {
  return ({
    train: '仅重训',
    p0: '跑 P0',
    env_finished: '补完赛环境',
    injury: '拉伤病',
    recalc_stale: '补齐过期预测',
  })[cta] || '执行'
}

async function runQualityCta(cta) {
  if (cta === 'train') return runTrainOnly()
  if (cta === 'p0') return runP0AndRefresh()
  if (cta === 'env_finished') return runEnvBackfill(true)
  if (cta === 'injury') return runInjuryCrawl()
  if (cta === 'recalc_stale') {
    await router.push('/model/overview')
    return recalculateUpcoming(true)
  }
}

/** store.runP0Pipeline 完成后只 bump dataEpoch；此处保证质量看板刷新 */
async function runP0AndRefresh() {
  await runP0Pipeline()
}

function stopUelPoll() {
  if (uelPollInterval) {
    clearInterval(uelPollInterval)
    uelPollInterval = null
  }
}

async function runUelCatchup() {
  if (uelCatchup.value.running || p0Pipeline.value.running) return
  uelCatchup.value = { running: true, message: 'UEL 补齐已提交...', error: false, jobId: '' }
  try {
    const res = await scheduleApi.runUelCatchup()
    const jobId = res?.job_id
    uelCatchup.value.jobId = jobId || ''
    uelCatchup.value.message = res?.message || 'UEL 补齐已入队'
    if (!jobId) {
      uelCatchup.value.running = false
      await fetchQuality()
      return
    }
    stopUelPoll()
    uelPollInterval = setInterval(async () => {
      try {
        const st = await scheduleApi.getJobStatus(jobId)
        const status = st?.status
        if (status === 'finished' || status === 'failed') {
          stopUelPoll()
          uelCatchup.value.running = false
          uelCatchup.value.error = status === 'failed'
          uelCatchup.value.message = status === 'failed'
            ? (st?.exc_info || 'UEL 补齐失败')
            : 'UEL 补齐完成，请查看覆盖率后如需可再训'
          await fetchQuality()
        }
      } catch (e) {
        stopUelPoll()
        uelCatchup.value.running = false
        uelCatchup.value.error = true
        uelCatchup.value.message = e?.message || '查询任务状态失败'
      }
    }, 5000)
  } catch (e) {
    uelCatchup.value.running = false
    uelCatchup.value.error = true
    uelCatchup.value.message = e?.message || 'UEL 补齐启动失败'
  }
}

function stopExtendedPoll() {
  if (extendedPollInterval) {
    clearInterval(extendedPollInterval)
    extendedPollInterval = null
  }
}

async function runExtendedCatchup() {
  if (extendedCatchup.value.running || p0Pipeline.value.running || uelCatchup.value.running) return
  extendedCatchup.value = { running: true, message: '扩展联赛补齐已提交...', error: false, jobId: '' }
  try {
    const res = await scheduleApi.runExtendedCatchup()
    const jobId = res?.job_id
    extendedCatchup.value.jobId = jobId || ''
    const leagueHint = (res?.leagues || []).join('/') || 'MLS/BRA/SWE/FIN/NOR/K1'
    extendedCatchup.value.message = res?.message || `${leagueHint} 补齐已入队`
    if (!jobId) {
      extendedCatchup.value.running = false
      await fetchQuality()
      return
    }
    stopExtendedPoll()
    extendedPollInterval = setInterval(async () => {
      try {
        const st = await scheduleApi.getJobStatus(jobId)
        const status = st?.status
        if (status === 'finished' || status === 'failed') {
          stopExtendedPoll()
          extendedCatchup.value.running = false
          extendedCatchup.value.error = status === 'failed'
          extendedCatchup.value.message = status === 'failed'
            ? (st?.exc_info || '扩展联赛补齐失败')
            : '扩展联赛补齐完成，可在质量表查看覆盖率后再「仅重训」'
          await fetchQuality()
        }
      } catch (e) {
        stopExtendedPoll()
        extendedCatchup.value.running = false
        extendedCatchup.value.error = true
        extendedCatchup.value.message = e?.message || '查询任务状态失败'
      }
    }, 5000)
  } catch (e) {
    extendedCatchup.value.running = false
    extendedCatchup.value.error = true
    extendedCatchup.value.message = e?.message || '扩展联赛补齐启动失败'
  }
}

function selectWeakTeam(team) {
  aliasDraft.value = {
    alias: team?.name || team?.short_name || team?.team_id || '',
    team_id: team?.team_id || '',
    espn_abbr: '',
    league_id: team?.league_id || '',
  }
}

async function fetchPendingAliases() {
  try {
    const res = await scheduleApi.listTeamAliases({ status: 'pending', limit: 50 })
    pendingAliases.value = res?.items || []
  } catch {
    pendingAliases.value = []
  }
}

async function saveTeamAlias() {
  if (!aliasDraft.value.alias || !aliasDraft.value.team_id || aliasSaving.value) return
  aliasSaving.value = true
  qualityError.value = null
  try {
    await scheduleApi.createTeamAlias({
      alias: aliasDraft.value.alias,
      team_id: aliasDraft.value.team_id,
      espn_abbr: aliasDraft.value.espn_abbr || null,
      league_id: aliasDraft.value.league_id || null,
      status: 'confirmed',
      source: 'manual',
    })
    envBackfill.value.message = `已确认别名「${aliasDraft.value.alias}」→ ${aliasDraft.value.team_id}`
    envBackfill.value.error = false
    aliasDraft.value = { alias: '', team_id: '', espn_abbr: '', league_id: '' }
    await fetchPendingAliases()
  } catch (e) {
    qualityError.value = e?.message || '保存别名失败'
  } finally {
    aliasSaving.value = false
  }
}

async function suggestTeamAliases() {
  aliasSaving.value = true
  qualityError.value = null
  try {
    const res = await scheduleApi.suggestTeamAliases()
    envBackfill.value.message = `已生成待确认别名 ${res?.created ?? 0} 条（跳过 ${res?.skipped ?? 0}）`
    envBackfill.value.error = false
    await fetchPendingAliases()
  } catch (e) {
    qualityError.value = e?.message || '生成待确认别名失败'
  } finally {
    aliasSaving.value = false
  }
}

async function confirmPendingAlias(row) {
  if (!row?.id || aliasSaving.value) return
  aliasSaving.value = true
  try {
    await scheduleApi.updateTeamAlias(row.id, {
      alias: row.alias,
      team_id: row.team_id,
      espn_abbr: row.espn_abbr,
      league_id: row.league_id,
      status: 'confirmed',
      note: row.note,
    })
    await fetchPendingAliases()
  } catch (e) {
    qualityError.value = e?.message || '确认别名失败'
  } finally {
    aliasSaving.value = false
  }
}

async function rejectPendingAlias(row) {
  if (!row?.id || aliasSaving.value) return
  aliasSaving.value = true
  try {
    await scheduleApi.updateTeamAlias(row.id, {
      alias: row.alias,
      team_id: row.team_id,
      espn_abbr: row.espn_abbr,
      league_id: row.league_id,
      status: 'rejected',
      note: row.note,
    })
    await fetchPendingAliases()
  } catch (e) {
    qualityError.value = e?.message || '忽略别名失败'
  } finally {
    aliasSaving.value = false
  }
}

watch(dataEpoch, () => {
  fetchQuality()
})

let unsubTrainingDone = null

onMounted(async () => {
  unsubTrainingDone = onTrainingDone(() => fetchQuality())
  await Promise.all([fetchQuality(), attachRunningP0()])
})

onBeforeUnmount(() => {
  stopUelPoll()
  stopExtendedPoll()
  if (unsubTrainingDone) unsubTrainingDone()
})
</script>

<style scoped>
.card-sub {
  font-size: 12px;
  color: var(--text-muted);
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.quality-card .card-header .card-actions {
  flex-wrap: wrap;
  gap: 8px;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: var(--transition);
}

.refresh-btn:hover:not(:disabled) {
  border-color: var(--color-blue);
  color: var(--color-blue);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.quality-card .quality-body {
  padding: 0 20px 16px;
}

.quality-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.quality-kpis .qk {
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.quality-kpis .qk.warn {
  border-color: rgba(var(--color-orange-rgb), 0.45);
  background: rgba(var(--color-orange-rgb), 0.08);
}

.quality-kpis .qk-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.quality-kpis b {
  font-size: 20px;
  color: var(--color-gold);
  font-weight: 600;
}

.quality-kpis .qk-sub {
  font-size: 11px;
  color: var(--text-muted, var(--text-secondary));
}

.quality-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.quality-actions .qa-item {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}

.quality-actions .qa-cta {
  margin-left: auto;
  font-size: 12px;
  padding: 4px 10px;
}

.quality-actions .qa-title {
  color: var(--text-primary);
  font-weight: 500;
}

.quality-actions .qa-action {
  color: var(--text-secondary);
  flex: 1 1 100%;
  font-size: 12px;
}

.quality-alerts {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.quality-alerts .qa-item {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
  font-size: 13px;
}

.quality-alerts .qa-title {
  color: var(--text-primary);
  font-weight: 500;
}

.quality-alerts .qa-action {
  color: var(--text-secondary);
  flex: 1 1 100%;
  font-size: 12px;
}

.quality-league-table .sla-miss {
  color: var(--color-orange, #ff9f43);
}

.quality-error {
  margin: 0 20px 12px;
  color: var(--color-red);
  font-size: 13px;
}

.quality-card .data-table.compact th,
.quality-card .data-table.compact td {
  padding: 8px 10px;
  font-size: 12px;
}

.gaps-panel {
  margin: 8px 20px 16px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.gaps-summary {
  font-size: 13px;
  color: var(--color-gold);
  margin-bottom: 8px;
}

.gaps-notes p {
  margin: 0 0 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.gaps-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
  margin: 12px 0;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-item label {
  font-size: 12px;
  color: var(--text-muted);
}

.gaps-filters select {
  min-width: 140px;
  padding: 6px 10px;
  font-size: 13px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.gaps-pagination {
  margin-top: 12px;
}

.weak-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.weak-tag {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  background: rgba(var(--color-gold-rgb), 0.08);
  border: 1px solid rgba(var(--color-gold-rgb), 0.2);
  color: var(--text-primary);
  cursor: pointer;
}

.weak-tag.active {
  border-color: var(--color-gold);
  background: rgba(var(--color-gold-rgb), 0.18);
}

.weak-tag small {
  color: var(--text-secondary);
  margin-left: 4px;
}

.alias-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 10px;
  margin-top: 12px;
}

.alias-form input {
  min-width: 120px;
  height: 32px;
  padding: 0 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.pending-aliases {
  margin-top: 16px;
}

.recalc-result {
  margin: 0 20px 16px;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  background: rgba(var(--color-green-rgb), 0.08);
  border: 1px solid rgba(var(--color-green-rgb), 0.25);
  color: var(--color-green);
  font-size: 13px;
}

.recalc-result.error {
  background: rgba(255, 77, 79, 0.08);
  border-color: rgba(255, 77, 79, 0.3);
  color: var(--color-red);
}

.empty-hint {
  text-align: center;
  color: var(--text-muted);
  padding: 16px 0;
  font-size: 13px;
}

.table-wrapper {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.data-table th {
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 12px;
}

.detail-section-title {
  margin: 16px 0 10px;
  font-size: 14px;
  color: var(--text-primary);
}
</style>
