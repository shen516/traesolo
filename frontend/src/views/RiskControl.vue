<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">风控体系</h1>
      <p class="page-subtitle">多维度风险识别与预警，保障预测结果可靠性</p>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="state-banner loading-banner">
      <span class="spinner"></span>
      <span>数据加载中...</span>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="state-banner error-banner">
      <span>⚠️ {{ error }}</span>
      <button class="retry-btn" @click="fetchAlerts()">重试</button>
    </div>

    <!-- 概览统计卡片 -->
    <div class="overview-grid">
      <div class="overview-card card" v-for="s in overviewStats" :key="s.label">
        <div class="overview-icon" :style="{ background: s.bg, color: s.color }">{{ s.icon }}</div>
        <div class="overview-info">
          <div class="overview-value" :style="{ color: s.color }">{{ s.value }}</div>
          <div class="overview-label">{{ s.label }}</div>
        </div>
      </div>
    </div>

    <div class="section-grid two-col">
      <!-- 风险预警列表 -->
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">风险预警列表</h2>
          <div class="card-actions">
            <label class="unprocessed-toggle">
              <input type="checkbox" v-model="followedOnly" @change="onFollowedToggle" />
              仅关注联赛
            </label>
            <label class="unprocessed-toggle">
              <input type="checkbox" v-model="onlyUnprocessed" @change="onUnprocessedToggle" />
              仅未处理
            </label>
            <span class="card-sub">{{ filteredAlerts.length }} 条 · 点击查看赛事详情，右侧可更新处理状态</span>
          </div>
        </div>
        <div class="level-filters">
          <button
            v-for="f in levelFilters"
            :key="f.key"
            class="level-filter-btn"
            :class="{ active: currentLevel === f.key }"
            @click="changeLevel(f.key)"
          >{{ f.label }}</button>
        </div>
        <div class="alert-list">
          <div v-if="!paginatedAlerts.length" class="empty-hint">暂无预警记录</div>
          <div
            v-for="alert in paginatedAlerts"
            :key="alert.id"
            class="alert-item"
            :class="['level-' + alert.level, { processed: alert.isProcessed }]"
            @click="goMatch(alert.matchId)"
          >
            <div class="alert-icon">{{ typeIcon(alert.type) }}</div>
            <div class="alert-body">
              <div class="alert-top">
                <span class="alert-type">{{ alert.type }}</span>
                <span class="alert-tags">
                  <span class="tag" :class="levelTagClass(alert.level)">{{ levelText(alert.level) }}</span>
                  <span class="tag" :class="alert.isProcessed ? 'tag-low' : 'tag-high'">
                    {{ alert.isProcessed ? '已处理' : '未处理' }}
                  </span>
                </span>
              </div>
              <div class="alert-match">{{ alert.match }}</div>
              <p v-if="alert.locked" class="alert-desc">
                <UpgradeHint inline text="升级旗舰版查看风控详情" />
              </p>
              <p v-else class="alert-desc">{{ alert.description }}</p>
              <div class="alert-time">{{ alert.time }}</div>
            </div>
            <div class="alert-aside">
              <button
                type="button"
                class="btn btn-sm"
                :class="alert.isProcessed ? 'btn-outline' : 'btn-primary'"
                :disabled="processingId === alert.id"
                @click.stop="toggleProcessed(alert)"
              >{{ processButtonText(alert) }}</button>
              <span class="alert-arrow">›</span>
            </div>
          </div>
        </div>
        <div class="alert-pagination" v-if="alertTotalPages > 1">
          <span class="page-info">第 {{ alertPage }} / {{ alertTotalPages }} 页</span>
          <div class="page-buttons">
            <button class="btn btn-sm" :disabled="alertPage <= 1" @click="alertPage--">上一页</button>
            <button class="btn btn-sm" :disabled="alertPage >= alertTotalPages" @click="alertPage++">下一页</button>
          </div>
        </div>
      </div>

      <!-- 风险等级分布饼图 -->
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">风险等级分布</h2>
          <span class="card-sub">各等级预警占比</span>
        </div>
        <div ref="pieChartRef" class="chart-box"></div>
        <div class="legend-list">
          <div class="legend-item" v-for="l in levelStats" :key="l.key">
            <span class="legend-dot" :style="{ background: l.color }"></span>
            <span class="legend-label">{{ l.label }}</span>
            <span class="legend-count" :style="{ color: l.color }">{{ l.count }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 风控策略说明 -->
    <CollapsibleSection title="风控策略说明" subtitle="识别规则、报告说明与过滤策略">
      <div class="section-grid three-col">
        <div class="card strategy-card" v-for="s in strategies" :key="s.title">
          <div class="strategy-icon" :style="{ color: s.color }">{{ s.icon }}</div>
          <h3 class="strategy-title">{{ s.title }}</h3>
          <p class="strategy-desc">{{ s.desc }}</p>
          <ul class="strategy-list">
            <li v-for="(item, idx) in s.points" :key="idx">{{ item }}</li>
          </ul>
        </div>
      </div>
    </CollapsibleSection>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { CHART_COLORS } from '@/utils/chartTheme'
import { useEChart } from '@/composables/useEChart'
import { riskApi } from '@/api'
import CollapsibleSection from '@/components/common/CollapsibleSection.vue'
import UpgradeHint from '@/components/UpgradeHint.vue'
import { useUserStore } from '@/stores/user'
import { useFollowsStore } from '@/stores/follows'
import { formatDateTime } from '@/utils/formatters'

const router = useRouter()
const userStore = useUserStore()
const followsStore = useFollowsStore()
const followedOnly = ref(!userStore.isAdmin)
const pieChartRef = ref(null)

const riskAlerts = ref([])
const onlyUnprocessed = ref(false)
const alertPage = ref(1)
const alertPageSize = 10
const loading = ref(false)
const error = ref(null)
const currentLevel = ref('all')
const processingId = ref(null)

const levelFilters = [
  { key: 'all', label: '全部' },
  { key: 'high', label: '高风险' },
  { key: 'mid', label: '中风险' },
  { key: 'low', label: '低风险' }
]

// 后端 type 枚举 -> 中文展示
const typeDisplayMap = {
  'data_abnormal': '数据异常',
  'high_risk': '高风险场次',
  'weather': '天气影响',
  'pitch': '场地条件',
  'injury': '伤病影响'
}

const typeIconMap = {
  '数据异常': '⚠️',
  '高风险场次': '🚨',
  '天气影响': '🌧️',
  '场地条件': '🏟️',
  '伤病影响': '🤕'
}

function typeIcon(type) {
  return typeIconMap[type] || '⚠️'
}

// 后端 snake_case 字段 -> 前端展示结构
function normalizeAlert(a) {
  return {
    id: a.id,
    matchId: a.match_id,
    match: a.match_name || '-',
    type: typeDisplayMap[a.type] || a.type,
    level: a.level,
    description: a.description || '',
    recommendedAction: a.recommended_action,
    locked: Array.isArray(a.locked_fields) && a.locked_fields.includes('description'),
    isProcessed: a.is_processed,
    time: formatDateTime(a.created_at)
  }
}

const filteredAlerts = computed(() => {
  let list = riskAlerts.value
  if (onlyUnprocessed.value) list = list.filter(a => !a.isProcessed)
  return list
})

const alertTotalPages = computed(() =>
  Math.max(1, Math.ceil(filteredAlerts.value.length / alertPageSize))
)

const paginatedAlerts = computed(() => {
  const start = (alertPage.value - 1) * alertPageSize
  return filteredAlerts.value.slice(start, start + alertPageSize)
})

watch(filteredAlerts, () => {
  if (alertPage.value > alertTotalPages.value) alertPage.value = 1
  nextTick(() => renderPieChart())
})

function onUnprocessedToggle() {
  alertPage.value = 1
}

function onFollowedToggle() {
  alertPage.value = 1
  fetchAlerts()
}

const levelStats = computed(() => {
  const source = filteredAlerts.value
  const count = k => source.filter(r => r.level === k).length
  return [
    { key: 'high', label: '高风险', count: count('high'), color: CHART_COLORS.red },
    { key: 'mid', label: '中风险', count: count('mid'), color: CHART_COLORS.orange },
    { key: 'low', label: '低风险', count: count('low'), color: CHART_COLORS.green }
  ]
})

const overviewStats = computed(() => [
  { label: '总预警数', value: riskAlerts.value.length, icon: '🛡️', color: 'var(--color-blue)', bg: 'rgba(var(--color-blue-rgb), 0.12)' },
  { label: '高风险', value: levelStats.value[0].count, icon: '🔴', color: 'var(--color-red)', bg: 'rgba(var(--color-red-rgb), 0.12)' },
  { label: '中风险', value: levelStats.value[1].count, icon: '🟠', color: 'var(--color-orange)', bg: 'rgba(var(--color-orange-rgb), 0.12)' },
  { label: '低风险', value: levelStats.value[2].count, icon: '🟢', color: 'var(--color-green)', bg: 'rgba(var(--color-green-rgb), 0.12)' }
])

function levelText(level) {
  return { high: '高风险', mid: '中风险', low: '低风险' }[level]
}

function levelTagClass(level) {
  return { high: 'tag-high', mid: 'tag-mid', low: 'tag-low' }[level]
}

function goMatch(matchId) {
  if (matchId) router.push(`/match/${matchId}`)
}

function processButtonText(alert) {
  if (processingId.value === alert.id) return '更新中...'
  return alert.isProcessed ? '标为未处理' : '标为已处理'
}

async function toggleProcessed(alert) {
  if (!alert?.id || processingId.value) return
  const next = !alert.isProcessed
  processingId.value = alert.id
  error.value = null
  try {
    await riskApi.setProcessed(alert.id, next)
    const row = riskAlerts.value.find(item => item.id === alert.id)
    if (row) row.isProcessed = next
  } catch (e) {
    error.value = e?.message || '更新处理状态失败'
  } finally {
    processingId.value = null
  }
}

const strategies = [
  {
    title: '风险识别与预警策略',
    icon: '🔍',
    color: 'var(--color-blue)',
    desc: '多维度实时监测比赛异常信号，自动触发预警机制，覆盖赛前与赛中各关键节点。',
    points: [
      '数据波动监测：识别球队近期表现的异常波动',
      '模型置信度评估：低置信度场次自动标记预警',
      '外部因素追踪：天气、场地、伤病等影响分析',
      '实时推送预警信息，提醒分析师重点关注'
    ]
  },
  {
    title: '风险评估报告说明',
    icon: '📋',
    color: 'var(--color-gold)',
    desc: '为每场预警生成结构化评估报告，量化风险等级并溯源关键影响因素。',
    points: [
      '风险等级三档划分：高风险、中风险、低风险',
      '风险因素溯源：定位关键不确定性来源',
      '置信度量化：模型预测可靠度评分',
      '参考建议：明确风险下结论的合理使用方式'
    ]
  },
  {
    title: '高风险场次过滤规则',
    icon: '🚫',
    color: 'var(--color-red)',
    desc: '设定严格过滤条件，规避高风险场次的预测误用，保障分析结论的稳健性。',
    points: [
      '高风险场次自动隐藏具体比分预测',
      '模型置信度低于阈值直接标记为高风险',
      '强强对话且实力接近场次自动归入高风险',
      '高风险场次仅展示趋势性参考结论'
    ]
  }
]

// 风险等级分布饼图 option 工厂
function buildPieChartOption() {
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [
      {
        type: 'pie',
        radius: ['50%', '72%'],
        center: ['50%', '50%'],
        itemStyle: { borderColor: CHART_COLORS.bgSecondary, borderWidth: 2 },
        label: { color: CHART_COLORS.textPrimary, fontSize: 12, formatter: '{b}\n{c}' },
        labelLine: { lineStyle: { color: CHART_COLORS.border } },
        data: levelStats.value
          .filter(l => l.count > 0)
          .map(l => ({ name: l.label, value: l.count, itemStyle: { color: l.color } }))
      }
    ]
  }
}

// 图表实例生命周期（init/setOption/resize/dispose）统一交给 useEChart 管理，render 幂等复用实例
const { render: renderPieChart } = useEChart(pieChartRef, buildPieChartOption)

async function fetchAlerts(level = currentLevel.value) {
  loading.value = true
  error.value = null
  try {
    const params = followedOnly.value
      ? { followed_only: true, include_children: followsStore.includeChildren }
      : {}
    const res = level === 'all'
      ? await riskApi.getAll(params)
      : await riskApi.getByLevel(level, params)
    // 后端返回 { alerts: [...] }
    const alerts = res?.alerts || res || []
    riskAlerts.value = alerts.map(normalizeAlert)
    await nextTick()
    renderPieChart()
  } catch (e) {
    error.value = e?.message || '数据加载失败，请检查后端服务'
  } finally {
    loading.value = false
  }
}

async function changeLevel(level) {
  currentLevel.value = level
  await fetchAlerts(level)
}

onMounted(() => {
  fetchAlerts()
})
</script>

<style scoped>
.page-container {
  height: 100%;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header {
  margin-bottom: 4px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.overview-card {
  display: flex;
  align-items: center;
  gap: 14px;
}

.overview-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}

.overview-info {
  display: flex;
  flex-direction: column;
}

.overview-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
}

.overview-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

.section-grid {
  display: grid;
  gap: 16px;
}

.two-col {
  grid-template-columns: 1.4fr 1fr;
}

.three-col {
  grid-template-columns: repeat(3, 1fr);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.unprocessed-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}

.alert-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.page-info {
  font-size: 12px;
  color: var(--text-muted);
}

.page-buttons {
  display: flex;
  gap: 8px;
}

.empty-hint {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.card-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.card-sub {
  font-size: 12px;
  color: var(--text-muted);
}

/* 预警列表 */
.alert-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.alert-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-left: 4px solid var(--text-muted);
  cursor: pointer;
  transition: var(--transition);
}

.alert-item.level-high {
  border-left-color: var(--color-red);
}

.alert-item.level-mid {
  border-left-color: var(--color-orange);
}

.alert-item.level-low {
  border-left-color: var(--color-green);
}

.alert-item:hover {
  background: var(--bg-hover);
  transform: translateX(2px);
}

.alert-item.level-high:hover {
  box-shadow: 0 0 16px rgba(var(--color-red-rgb), 0.25);
}

.alert-item.level-mid:hover {
  box-shadow: 0 0 16px rgba(var(--color-orange-rgb), 0.25);
}

.alert-icon {
  font-size: 22px;
  flex-shrink: 0;
  margin-top: 2px;
}

.alert-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.alert-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.alert-tags {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.alert-type {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.alert-match {
  font-size: 13px;
  color: var(--color-gold);
  font-weight: 600;
}

.alert-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.alert-time {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.alert-aside {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  gap: 8px;
  flex-shrink: 0;
  align-self: center;
}

.alert-arrow {
  font-size: 20px;
  color: var(--text-muted);
  align-self: center;
  transition: var(--transition);
}

.alert-item:hover .alert-arrow {
  color: var(--color-blue);
  transform: translateX(2px);
}

.alert-item.processed {
  opacity: 0.72;
}

.btn-sm {
  padding: 5px 12px;
  font-size: 12px;
  white-space: nowrap;
}

/* 饼图 */
.chart-box {
  width: 100%;
  height: 280px;
}

.legend-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary);
}

.legend-count {
  font-size: 15px;
  font-weight: 700;
}

/* 策略卡片 */
.strategy-card {
  display: flex;
  flex-direction: column;
}

.strategy-icon {
  font-size: 28px;
  margin-bottom: 12px;
}

.strategy-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.strategy-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 14px;
}

.strategy-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px dashed var(--border-color);
}

.strategy-list li {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  padding-left: 16px;
  position: relative;
}

.strategy-list li::before {
  content: '▸';
  position: absolute;
  left: 0;
  color: var(--color-blue);
}

/* 等级筛选 */
.level-filters {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.level-filter-btn {
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: var(--transition);
}

.level-filter-btn:hover {
  border-color: var(--color-blue);
  color: var(--color-blue);
}

.level-filter-btn.active {
  background: var(--color-blue);
  border-color: var(--color-blue);
  color: #fff;
}

/* 加载与错误状态 */
.state-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-radius: var(--radius-md);
  font-size: 14px;
}

.loading-banner {
  background: rgba(var(--color-blue-rgb), 0.08);
  border: 1px solid rgba(var(--color-blue-rgb), 0.25);
  color: var(--color-blue);
}

.error-banner {
  background: rgba(var(--color-red-rgb), 0.08);
  border: 1px solid rgba(var(--color-red-rgb), 0.3);
  color: var(--color-red);
  justify-content: space-between;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(var(--color-blue-rgb), 0.3);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.retry-btn {
  padding: 4px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-red);
  background: transparent;
  color: var(--color-red);
  font-size: 12px;
  cursor: pointer;
  transition: var(--transition);
}

.retry-btn:hover {
  background: var(--color-red);
  color: #fff;
}
</style>
