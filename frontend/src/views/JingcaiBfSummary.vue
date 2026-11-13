<template>
  <div class="jingcai-page">
    <div class="page-head card">
      <div class="page-head-main">
        <h1 class="page-title">分析汇总</h1>
        <p class="page-sub">
          汇总历史比分页已过开赛的场次。上月为完整自然月，本月截至今天已开赛场次。仅供分析，不构成投注建议。
        </p>
      </div>
    </div>

    <div class="filter-bar card">
      <div class="filter-section">
        <span class="filter-label">联赛</span>
        <select v-model="selectedLeague" class="filter-select" @change="loadData">
          <option value="">{{ followedOnly ? '关注的联赛' : '全部联赛' }}</option>
          <option v-for="lg in displayLeagues" :key="lg.id" :value="lg.id">
            {{ lg.icon || '⚽' }} {{ lg.name }}
          </option>
        </select>
      </div>
      <label class="filter-check">
        <input type="checkbox" v-model="followedOnly" @change="loadData" />
        仅关注
      </label>
      <label v-if="followedOnly" class="filter-check">
        <input type="checkbox" :checked="followsStore.includeChildren" @change="onIncludeChildrenChange" />
        含下级
      </label>
      <button class="btn btn-sm btn-primary" :disabled="loading" @click="loadData">
        {{ loading ? '汇总中...' : '刷新' }}
      </button>
      <span v-if="report" class="result-hint">截至 {{ report.as_of }}</span>
    </div>

    <div v-if="loading" class="empty-state">
      <div class="empty-icon">⏳</div>
      <div class="empty-text">数据加载中...</div>
    </div>
    <div v-else-if="errorMsg" class="empty-state">
      <div class="empty-icon">⚠️</div>
      <div class="empty-text">{{ emptyFollows ? '暂无关注联赛' : '加载失败' }}</div>
      <div class="empty-hint">{{ errorMsg }}</div>
      <button v-if="!emptyFollows" class="btn btn-primary" @click="loadData">重新加载</button>
    </div>
    <template v-else-if="lastPeriod && thisPeriod">
      <div class="period-grid">
        <section v-for="period in [lastPeriod, thisPeriod]" :key="period.key" class="card period-card">
          <header class="period-head">
            <div>
              <h2>{{ period.key === 'last_month' ? '上月' : '本月已出' }} {{ period.label }}</h2>
              <p>{{ period.from }} ~ {{ period.to }}</p>
            </div>
            <span v-if="period.partial" class="tag tag-info">未满月</span>
          </header>
          <p v-if="period.partial" class="partial-note">未满月，占比可以和上月对照，场次还不是整月。</p>

          <div class="kpi-grid">
            <div class="kpi">
              <span>场次</span>
              <b>{{ period.coverage.matches }}</b>
            </div>
            <div class="kpi">
              <span>已完赛</span>
              <b>{{ period.coverage.finished }}</b>
            </div>
            <div class="kpi">
              <span>缺比分</span>
              <b class="warn">{{ period.coverage.missing }}</b>
            </div>
            <div class="kpi">
              <span>联赛</span>
              <b>{{ period.coverage.leagues }}</b>
            </div>
          </div>

          <div class="block">
            <h3>赛果分布</h3>
            <div v-if="!period.results.sample" class="muted">暂无已完赛场次</div>
            <div v-else class="outcome-list">
              <div v-for="item in outcomeRows(period)" :key="item.key" class="outcome-row">
                <span class="outcome-name">{{ item.label }}</span>
                <div class="bar-track">
                  <div class="bar-fill" :class="item.key" :style="{ width: barWidth(item.rate) }"></div>
                </div>
                <span class="outcome-num">{{ item.count }} · {{ pct(item.rate) }}</span>
                <span v-if="period.key === 'this_month'" class="delta">{{ deltaText(item.rate, lastRate(item.key)) }}</span>
              </div>
            </div>
            <p v-if="period.goals.sample" class="goal-line">
              场均 {{ fmtNum(period.goals.avg_total) }} 球
              （主 {{ fmtNum(period.goals.avg_home) }} / 客 {{ fmtNum(period.goals.avg_away) }}）
              · 双方进球 {{ pct(period.goals.both_scored_rate) }}
              · 零封 {{ pct(period.goals.clean_sheet_rate) }}
              <span v-if="period.key === 'this_month'" class="delta">{{ deltaText(period.goals.avg_total, lastPeriod.goals.avg_total, false) }}</span>
            </p>
          </div>

          <div class="block">
            <h3>比分出现次数</h3>
            <div v-if="!period.score_freq.length" class="muted">暂无已完赛比分</div>
            <ol v-else class="score-list">
              <li v-for="item in period.score_freq" :key="item.score">
                <b>{{ item.score }}</b>
                <span>{{ item.count }} 场 · {{ pct(item.rate) }}</span>
              </li>
            </ol>
            <p class="muted other-line">
              胜其它 {{ period.score_other['胜其它'] }}
              · 平其它 {{ period.score_other['平其它'] }}
              · 负其它 {{ period.score_other['负其它'] }}
            </p>
          </div>

          <div class="block">
            <h3>比分 SP 对照</h3>
            <UpgradeHint
              v-if="period.sp_compare.locked"
              text="免费版不展示比分 SP 对照，升级专业版可查看最低 SP 与赛果是否一致"
            />
            <div v-else-if="!period.sp_compare.sample" class="muted">没有 31 个比分 SP 都齐全的已完赛场次</div>
            <div v-else class="sp-grid">
              <div class="kpi">
                <span>对照样本</span>
                <b>{{ period.sp_compare.sample }}</b>
              </div>
              <div class="kpi">
                <span>最低 SP 一致</span>
                <b>{{ pct(period.sp_compare.top1_rate) }}</b>
                <small>{{ period.sp_compare.top1_hits }}/{{ period.sp_compare.sample }}</small>
                <span v-if="period.key === 'this_month'" class="delta">{{ deltaText(period.sp_compare.top1_rate, lastPeriod.sp_compare.top1_rate) }}</span>
              </div>
              <div class="kpi">
                <span>前三 SP 覆盖</span>
                <b>{{ pct(period.sp_compare.top3_rate) }}</b>
                <small>{{ period.sp_compare.top3_hits }}/{{ period.sp_compare.sample }}</small>
                <span v-if="period.key === 'this_month'" class="delta">{{ deltaText(period.sp_compare.top3_rate, lastPeriod.sp_compare.top3_rate) }}</span>
              </div>
            </div>
            <p v-if="!period.sp_compare.locked" class="muted">最低 SP 指该场 31 个比分里数值最低的一项，只作赛果对照。</p>
          </div>

          <div class="block">
            <h3>让球结果</h3>
            <div v-if="!period.handicap.sample" class="muted">没有可计算让球结果的已完赛场次</div>
            <p v-else class="goal-line">
              让胜 {{ period.handicap.H.count }}（{{ pct(period.handicap.H.rate) }}）
              · 让平 {{ period.handicap.D.count }}（{{ pct(period.handicap.D.rate) }}）
              · 让负 {{ period.handicap.A.count }}（{{ pct(period.handicap.A.rate) }}）
            </p>
          </div>
        </section>
      </div>

      <div class="chart-grid">
        <section class="card">
          <h2 class="chart-title">比分出现次数对照</h2>
          <div v-show="hasScores" ref="scoreChartRef" class="chart"></div>
          <p v-if="!hasScores" class="muted">两个月份都还没有已完赛比分</p>
        </section>
        <section class="card">
          <h2 class="chart-title">总进球分布</h2>
          <div v-show="hasGoals" ref="goalChartRef" class="chart"></div>
          <p v-if="!hasGoals" class="muted">两个月份都还没有已完赛进球</p>
        </section>
      </div>

      <section class="card">
        <h2 class="chart-title">联赛拆分</h2>
        <p v-if="!leagueRows.length" class="muted">暂无联赛样本</p>
        <div v-else class="table-wrap">
          <table class="league-table">
            <thead>
              <tr>
                <th>联赛</th>
                <th>上月场次</th>
                <th>上月主胜</th>
                <th>上月常见比分</th>
                <th v-if="!spLocked">上月最低 SP</th>
                <th>本月场次</th>
                <th>本月主胜</th>
                <th>本月常见比分</th>
                <th v-if="!spLocked">本月最低 SP</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in leagueRows" :key="row.id">
                <td>{{ row.name }}</td>
                <td>{{ cellCount(row.last) }}</td>
                <td>{{ cellRate(row.last) }}</td>
                <td>{{ row.last?.top_score || '-' }}</td>
                <td v-if="!spLocked">{{ cellSp(row.last) }}</td>
                <td>{{ cellCount(row.current) }}</td>
                <td>{{ cellRate(row.current) }}</td>
                <td>{{ row.current?.top_score || '-' }}</td>
                <td v-if="!spLocked">{{ cellSp(row.current) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { matchApi } from '@/api'
import { getActiveLeagues } from '@/utils/catalogCache'
import { useEChart } from '@/composables/useEChart'
import UpgradeHint from '@/components/UpgradeHint.vue'
import { useUserStore } from '@/stores/user'
import { useFollowsStore } from '@/stores/follows'

const userStore = useUserStore()
const followsStore = useFollowsStore()
const followedOnly = ref(!userStore.isAdmin)
const selectedLeague = ref('')
const leagues = ref([])
const loading = ref(false)
const errorMsg = ref('')
const emptyFollows = ref(false)
const report = ref(null)
const scoreChartRef = ref(null)
const goalChartRef = ref(null)

const OUTCOMES = [
  { key: 'H', label: '主胜' },
  { key: 'D', label: '平' },
  { key: 'A', label: '客胜' },
]

const lastPeriod = computed(() => report.value?.periods?.find((item) => item.key === 'last_month') || null)
const thisPeriod = computed(() => report.value?.periods?.find((item) => item.key === 'this_month') || null)
const spLocked = computed(() => !!report.value?.sp_locked)
const hasScores = computed(() => {
  const periods = [lastPeriod.value, thisPeriod.value]
  return periods.some((period) => (period?.score_freq || []).length)
})
const hasGoals = computed(() => {
  const periods = [lastPeriod.value, thisPeriod.value]
  return periods.some((period) => (period?.goals?.sample || 0) > 0)
})
const displayLeagues = computed(() => {
  if (!followedOnly.value || !followsStore.ids.length) return leagues.value
  return leagues.value.filter((item) => followsStore.queryIdSet.has(item.id))
})
const leagueRows = computed(() => {
  const map = new Map()
  const pull = (period, side) => {
    for (const row of period?.by_league || []) {
      const id = row.league_id || row.league_name
      if (!map.has(id)) map.set(id, { id, name: row.league_name || id, last: null, current: null })
      map.get(id)[side] = row
    }
  }
  pull(lastPeriod.value, 'last')
  pull(thisPeriod.value, 'current')
  return [...map.values()].sort((a, b) => {
    const total = (row) => (row.last?.matches || 0) + (row.current?.matches || 0)
    return total(b) - total(a) || String(a.name).localeCompare(String(b.name), 'zh')
  })
})

function pct(rate) {
  if (rate == null || Number.isNaN(Number(rate))) return '-'
  return `${(Number(rate) * 100).toFixed(1)}%`
}

function fmtNum(value) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(2)
}

function deltaText(current, previous, asPoint = true) {
  if (current == null || previous == null) return ''
  const diff = asPoint ? (Number(current) - Number(previous)) * 100 : Number(current) - Number(previous)
  if (!Number.isFinite(diff)) return ''
  const sign = diff > 0 ? '+' : ''
  const digits = asPoint ? diff.toFixed(1) : diff.toFixed(2)
  return `较上月 ${sign}${digits}${asPoint ? ' pt' : ''}`
}

function lastRate(key) {
  return lastPeriod.value?.results?.[key]?.rate
}

function outcomeRows(period) {
  return OUTCOMES.map((item) => ({
    ...item,
    count: period.results?.[item.key]?.count || 0,
    rate: period.results?.[item.key]?.rate,
  }))
}

function barWidth(rate) {
  const value = Number(rate)
  if (!Number.isFinite(value) || value <= 0) return '0%'
  return `${Math.min(100, value * 100)}%`
}

function cellCount(row) {
  if (!row) return '-'
  return `${row.matches} / 完赛 ${row.finished}`
}

function cellRate(row) {
  if (!row || !row.finished) return '-'
  return pct(row.home_rate)
}

function cellSp(row) {
  if (!row || row.sp_top1_rate == null) return '-'
  return pct(row.sp_top1_rate)
}

function listParams() {
  const params = {}
  if (selectedLeague.value) params.league_id = selectedLeague.value
  if (followedOnly.value) params.league_ids = followsStore.queryIds.join(',')
  return params
}

function axisStyle() {
  return {
    axisLine: { lineStyle: { color: '#2d4f7a' } },
    axisLabel: { color: '#c5d2e6' },
    splitLine: { lineStyle: { color: 'rgba(45, 79, 122, 0.45)' } },
  }
}

// 比分对照柱状图 option 工厂：两个月份都无已完赛比分时返回 null
function buildScoreChartOption() {
  if (!hasScores.value) return null
  const categories = []
  const seen = new Set()
  for (const period of [lastPeriod.value, thisPeriod.value]) {
    for (const item of period?.score_freq || []) {
      if (seen.has(item.score)) continue
      seen.add(item.score)
      categories.push(item.score)
    }
  }
  const countOf = (period, score) => (period?.score_freq || []).find((item) => item.score === score)?.count || 0
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#c5d2e6' }, top: 0 },
    grid: { left: 36, right: 12, top: 36, bottom: 28 },
    xAxis: { type: 'category', data: categories, ...axisStyle() },
    yAxis: { type: 'value', minInterval: 1, ...axisStyle() },
    series: [
      { name: '上月', type: 'bar', data: categories.map((score) => countOf(lastPeriod.value, score)), itemStyle: { color: '#ffd700' } },
      { name: '本月已出', type: 'bar', data: categories.map((score) => countOf(thisPeriod.value, score)), itemStyle: { color: '#4de0ff' } },
    ],
  }
}

// 总进球分布柱状图 option 工厂：两个月份都无进球样本时返回 null
function buildGoalChartOption() {
  if (!hasGoals.value) return null
  const labels = (lastPeriod.value?.goals?.distribution || thisPeriod.value?.goals?.distribution || []).map((item) => item.label)
  const dist = (period, label) => (period?.goals?.distribution || []).find((item) => item.label === label)?.count || 0
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#c5d2e6' }, top: 0 },
    grid: { left: 36, right: 12, top: 36, bottom: 28 },
    xAxis: { type: 'category', data: labels, name: '总进球', ...axisStyle() },
    yAxis: { type: 'value', minInterval: 1, ...axisStyle() },
    series: [
      { name: '上月', type: 'bar', data: labels.map((label) => dist(lastPeriod.value, label)), itemStyle: { color: '#ffd700' } },
      { name: '本月已出', type: 'bar', data: labels.map((label) => dist(thisPeriod.value, label)), itemStyle: { color: '#4de0ff' } },
    ],
  }
}

// 图表实例生命周期（init/setOption/resize/dispose）统一交给 useEChart 管理
const { render: renderScoreChart } = useEChart(scoreChartRef, buildScoreChartOption)
const { render: renderGoalChart } = useEChart(goalChartRef, buildGoalChartOption)

// 图表容器是 v-show：隐藏时尺寸为 0，须等数据就绪（hasScores/hasGoals 为 true）且 DOM 更新后再 render，避免 0 尺寸实例
function renderCharts() {
  if (hasScores.value) renderScoreChart()
  if (hasGoals.value) renderGoalChart()
}

async function loadData() {
  loading.value = true
  errorMsg.value = ''
  try {
    await followsStore.ensureLoaded()
    if (followedOnly.value && !followsStore.ids.length) {
      report.value = null
      emptyFollows.value = true
      errorMsg.value = '还没有关注联赛，可取消「仅关注」查看全部'
      return
    }
    emptyFollows.value = false
    report.value = await matchApi.getJingcaiBfSummary(listParams())
  } catch (e) {
    report.value = null
    emptyFollows.value = false
    errorMsg.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loading.value = false
    await nextTick()
    renderCharts()
  }
}

async function onIncludeChildrenChange(e) {
  await followsStore.setIncludeChildren(e.target.checked)
  await loadData()
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
  padding: 18px 20px;
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

.filter-section,
.filter-check {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-check {
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}

.filter-label,
.result-hint,
.muted {
  color: var(--text-muted);
  font-size: 0.85rem;
}

.filter-select {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 6px;
  padding: 6px 10px;
  min-width: 140px;
}

.empty-state {
  text-align: center;
  padding: 48px 16px;
}

.empty-icon {
  font-size: 2rem;
  margin-bottom: 8px;
}

.empty-text {
  color: var(--text-primary);
  margin-bottom: 6px;
}

.empty-hint {
  color: var(--text-muted);
  margin-bottom: 12px;
}

.period-grid,
.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.period-card h2,
.chart-title {
  margin: 0;
  font-size: 1rem;
  color: var(--text-primary);
}

.period-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.period-head p,
.partial-note {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.kpi-grid,
.sp-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-top: 14px;
}

.sp-grid {
  grid-template-columns: repeat(3, 1fr);
}

.kpi {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kpi span,
.kpi small {
  color: var(--text-muted);
  font-size: 12px;
}

.kpi b {
  font-size: 1.25rem;
  color: var(--text-primary);
}

.kpi b.warn {
  color: var(--color-orange);
}

.block {
  margin-top: 16px;
}

.block h3 {
  margin: 0 0 8px;
  font-size: 0.92rem;
  color: var(--text-secondary);
}

.outcome-row {
  display: grid;
  grid-template-columns: 42px 1fr auto auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.outcome-name,
.outcome-num,
.delta {
  font-size: 12px;
  color: var(--text-secondary);
}

.delta {
  color: var(--color-gold);
  min-width: 92px;
}

.bar-track {
  height: 8px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 99px;
}

.bar-fill.H { background: var(--color-green); }
.bar-fill.D { background: var(--color-gold); }
.bar-fill.A { background: var(--color-blue); }

.goal-line,
.other-line {
  margin: 8px 0 0;
  line-height: 1.5;
}

.score-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 16px;
}

.score-list li {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.score-list b {
  color: var(--text-primary);
}

.chart {
  height: 280px;
}

.table-wrap {
  overflow-x: auto;
  margin-top: 12px;
}

.league-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.league-table th,
.league-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-color);
  text-align: left;
  white-space: nowrap;
}

.league-table th {
  color: var(--text-muted);
  font-weight: 600;
}

@media (max-width: 1100px) {
  .period-grid,
  .chart-grid {
    grid-template-columns: 1fr;
  }
  .kpi-grid,
  .sp-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
