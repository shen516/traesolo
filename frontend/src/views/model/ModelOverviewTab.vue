<template>
  <div class="model-overview-tab">
    <div class="overview-grid">
      <div class="overview-card card" v-for="item in overviewStats" :key="item.label">
        <div class="overview-icon" :style="{ background: item.bg, color: item.color }">{{ item.icon }}</div>
        <div class="overview-info">
          <div class="overview-value" :style="{ color: item.color }">{{ item.value }}</div>
          <div class="overview-label">{{ item.label }}</div>
        </div>
      </div>
    </div>

    <div class="card chart-card">
      <div class="card-header">
        <h2 class="card-title">模型权重配置</h2>
        <span class="card-sub">四模型加权融合（全局）</span>
      </div>
      <div ref="weightChartRef" class="chart-box"></div>
      <div class="weight-bars">
        <div class="weight-item" v-for="w in modelWeights" :key="w.name">
          <div class="weight-row">
            <span class="weight-icon">{{ w.icon }}</span>
            <span class="weight-name">{{ w.name }}</span>
            <span class="weight-value" :style="{ color: w.color }">{{ (w.weight * 100).toFixed(0) }}%</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: (w.weight * 100) + '%', background: w.color }"></div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="staleStats || recalcState.running || recalcState.message"
      class="card recalc-card"
    >
      <div class="card-header">
        <h2 class="card-title">未赛预测同步</h2>
        <div class="card-actions">
          <span class="card-sub" v-if="staleStats">
            扫描 {{ staleStats.scanned }} · 缺预测 {{ staleStats.missing_prediction }} · 过期 {{ staleStats.stale_prediction }}
            <template v-if="staleStats.missing_scenarios != null"> · 缺场景 {{ staleStats.missing_scenarios }}</template>
            · 待处理 {{ staleStats.needs_recalc }}
            <template v-if="staleStats.model_version"> · 当前 {{ staleStats.model_version }}</template>
          </span>
          <button class="refresh-btn" @click="fetchStaleStats" :disabled="recalcState.running || staleStatsLoading">
            {{ staleStatsLoading ? '统计中...' : '刷新统计' }}
          </button>
          <button
            class="btn btn-primary"
            @click="recalculateUpcoming(true)"
            :disabled="recalcState.running || !(staleStats?.needs_recalc > 0)"
            title="仅重算缺 meta / 版本落后 / 未预测的未赛"
          >
            <span v-if="recalcState.running && recalcState.mode === 'stale'" class="btn-spinner"></span>
            {{ recalcState.running && recalcState.mode === 'stale' ? '重算中...' : '一键补齐过期未赛' }}
          </button>
          <button
            class="btn btn-outline"
            @click="recalculateUpcoming(false)"
            :disabled="recalcState.running"
            title="强制按当前模型重算近期未赛（最多 80 场）"
          >
            <span v-if="recalcState.running && recalcState.mode === 'force'" class="btn-spinner"></span>
            {{ recalcState.running && recalcState.mode === 'force' ? '重算中...' : '强制重算近期未赛' }}
          </button>
        </div>
      </div>
      <p class="recalc-hint">
        训练或切换模型后，旧预测可能缺少融合细节 / <strong>分析场景</strong>（scenarios）或仍标注旧版本。
        用此处批量按<strong>当前模型</strong>原地更新，详情页即可切换整合版 / ELO / 泊松等场景。
      </p>
      <p v-if="recalcState.message" class="recalc-result" :class="{ error: recalcState.error }">{{ recalcState.message }}</p>
    </div>

    <div class="card">
      <div class="card-header">
        <h2 class="card-title">模型实时状态</h2>
        <div class="card-actions">
          <button class="refresh-btn" @click="refresh" :disabled="overviewLoading">
            <span v-if="overviewLoading" class="btn-spinner"></span>
            刷新
          </button>
          <button class="btn btn-primary" @click="startTraining" :disabled="isTraining">
            <span v-if="isTraining" class="btn-spinner"></span>
            {{ isTraining ? '训练中...' : '开始训练' }}
          </button>
          <div class="auto-refresh">
            <label class="switch">
              <input type="checkbox" v-model="autoRefresh" />
              <span class="slider"></span>
            </label>
            <span>自动刷新</span>
          </div>
        </div>
      </div>
      <div class="model-status-grid">
        <div
          class="status-card"
          v-for="model in modelStatusDetail"
          :key="model.key"
          :class="{ running: model.status === 'running' }"
        >
          <div class="status-header">
            <div class="status-icon" :class="model.key">
              {{ getModelIcon(model.key) }}
            </div>
            <div class="status-info">
              <h4 class="status-name">{{ model.name }}</h4>
              <span class="status-tag" :class="model.status">{{ model.status === 'running' ? '运行中' : '停止' }}</span>
            </div>
          </div>
          <p class="status-desc">{{ model.description }}</p>
          <div class="status-params">
            <div class="params-title">核心参数</div>
            <div class="param-item" v-for="(value, label) in model.key_params" :key="label">
              <span class="param-label">{{ getParamLabel(model.key, label) }}</span>
              <span class="param-value" :style="{ color: getModelColor(model.key) }">{{ value }}</span>
            </div>
          </div>
          <div v-if="Object.keys(model.loaded_data).length" class="status-data">
            <div class="data-item" v-for="(value, label) in model.loaded_data" :key="label">
              <span class="data-label">{{ getDataLabel(label) }}</span>
              <span class="data-value">{{ value }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <CollapsibleSection title="算法说明" subtitle="各子模型原理与示例参数">
      <div class="section-grid three-col">
        <div class="card algo-card" v-for="algo in algorithmCards" :key="algo.title">
          <div class="algo-icon" :style="{ color: algo.color }">{{ algo.icon }}</div>
          <h3 class="algo-title">{{ algo.title }}</h3>
          <p class="algo-principle">{{ algo.principle }}</p>
          <div class="algo-params">
            <div class="params-title">核心参数</div>
            <div class="param-item" v-for="p in algo.params" :key="p.label">
              <span class="param-label">{{ p.label }}</span>
              <span class="param-value" :style="{ color: algo.color }">{{ p.value }}</span>
            </div>
          </div>
        </div>
      </div>
    </CollapsibleSection>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import echarts from '@/utils/echarts'
import { CHART_COLORS, MODEL_COLORS } from '@/utils/chartTheme'
import CollapsibleSection from '@/components/common/CollapsibleSection.vue'
import {
  modelStatus, modelStatusDetail, currentVersion,
  overviewLoading,
  isTraining, startTraining, fetchOverviewData,
  staleStats, staleStatsLoading, recalcState,
  fetchStaleStats, recalculateUpcoming,
} from './modelStore'

// ---------- 权重卡片与图 ----------

const weightChartRef = ref(null)
let weightChart = null

const modelWeights = ref([
  { name: '泊松模型', key: 'poisson', weight: 0.30, color: MODEL_COLORS.poisson, icon: '📊' },
  { name: 'ELO评级', key: 'elo', weight: 0.30, color: MODEL_COLORS.elo, icon: '⚔️' },
  { name: 'xG模型', key: 'xg', weight: 0.20, color: MODEL_COLORS.xg, icon: '🎯' },
  { name: '蒙特卡洛', key: 'monte_carlo', weight: 0.20, color: MODEL_COLORS.monte_carlo, icon: '🎲' },
])

function applyWeightsFromStatus(weights) {
  if (!weights) return
  modelWeights.value = modelWeights.value.map(item => ({
    ...item,
    weight: weights[item.key] != null ? Number(weights[item.key]) : item.weight,
  }))
}

function initWeightChart() {
  if (!weightChartRef.value) return
  if (!weightChart) weightChart = echarts.init(weightChartRef.value)
  weightChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
    legend: { bottom: 0, textStyle: { color: CHART_COLORS.textMuted, fontSize: 12 } },
    series: [
      {
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: CHART_COLORS.bgSecondary, borderWidth: 2 },
        label: { color: CHART_COLORS.textPrimary, fontSize: 12, formatter: '{b}\n{d}%' },
        labelLine: { lineStyle: { color: CHART_COLORS.textMuted } },
        data: modelWeights.value.map(w => ({
          name: w.name,
          value: w.weight,
          itemStyle: { color: w.color }
        }))
      }
    ]
  })
}

function handleResize() {
  weightChart?.resize()
}

// ---------- 自动刷新 ----------

const autoRefresh = ref(false)
let refreshInterval = null

watch(autoRefresh, (val) => {
  if (val) {
    refreshInterval = setInterval(refresh, 15000)
  } else {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
})

async function refresh() {
  await fetchOverviewData()
  applyWeightsFromStatus(modelStatus.value?.weights)
  await nextTick()
  initWeightChart()
}

// ---------- 概览统计卡 ----------

const overviewStats = computed(() => {
  const version = modelStatus.value?.version || currentVersion.value?.version || '-'
  let accuracy = '-'
  if (modelStatus.value?.accuracy != null) {
    accuracy = (modelStatus.value.accuracy * 100).toFixed(1) + '%'
  } else if (currentVersion.value?.accuracy != null) {
    accuracy = currentVersion.value.accuracy + '%'
  }
  return [
    { label: '当前版本', value: version, icon: '🏷️', color: 'var(--color-blue)', bg: 'rgba(var(--color-blue-rgb), 0.12)' },
    { label: '模型准确率', value: accuracy, icon: '🎯', color: 'var(--color-green)', bg: 'rgba(var(--color-green-rgb), 0.12)' },
    { label: '上次训练', value: modelStatus.value?.last_train || '-', icon: '🔄', color: 'var(--color-gold)', bg: 'rgba(var(--color-gold-rgb), 0.12)' },
    { label: '训练样本', value: modelStatus.value?.training_sample ?? '-', icon: '📡', color: 'var(--color-orange)', bg: 'rgba(var(--color-orange-rgb), 0.12)' }
  ]
})

const algorithmCards = [
  {
    title: '泊松模型',
    icon: '📊',
    color: 'var(--color-blue)',
    principle: '基于泊松分布对进球数进行建模，通过两队攻防强度计算期望进球数 λ，进而推导各比分概率分布。',
    params: [
      { label: '主队期望进球 λHome', value: '1.85' },
      { label: '客队期望进球 λAway', value: '1.32' },
      { label: '权重系数', value: '0.30' }
    ]
  },
  {
    title: 'ELO评级',
    icon: '⚔️',
    color: 'var(--color-gold)',
    principle: '通过双方 ELO 评级差计算胜率期望，引入联赛等级系数动态调整，反映球队长期实力对比。',
    params: [
      { label: '主队 ELO', value: '2085' },
      { label: '客队 ELO', value: '2020' },
      { label: '联赛等级系数', value: '动态' }
    ]
  },
  {
    title: 'xG模型',
    icon: '🎯',
    color: 'var(--color-green)',
    principle: '基于射门位置、方式、距离等特征计算预期进球 xG，量化球队真实进攻威胁，集成权重最高。',
    params: [
      { label: '主队 xG', value: '2.10' },
      { label: '客队 xG', value: '1.25' },
      { label: '权重系数', value: '0.40' }
    ]
  }
]

function getModelIcon(key) {
  const icons = { poisson: '📊', elo: '⚔️', xg: '🎯', monte_carlo: '🎲' }
  return icons[key] || '📦'
}

function getModelColor(key) {
  return MODEL_COLORS[key] || CHART_COLORS.textMuted
}

function getParamLabel(modelKey, paramKey) {
  const labels = {
    poisson: { max_goals: '最大进球数', home_advantage: '主场优势系数' },
    elo: { k_factor: 'K因子', home_advantage: '主场加成', initial_rating: '初始评级' },
    xg: {
      prior_xg_per_shot: '射门转化先验',
      prior_xg_per_sot: '射正转化先验',
      shrink_k: '收缩系数',
      min_matches: '最少样本场次',
    },
    monte_carlo: { simulations: '模拟次数' },
  }
  return labels[modelKey]?.[paramKey] || paramKey
}

function getDataLabel(key) {
  const labels = { leagues_count: '联赛数量', teams_count: '球队数量' }
  return labels[key] || key
}

defineExpose({
  /** 父页在 keep-alive 重入或 tab 切回时调用：补初始化图表 */
  reinitCharts() {
    nextTick(() => initWeightChart())
  },
})

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  await fetchOverviewData()
  applyWeightsFromStatus(modelStatus.value?.weights)
  await nextTick()
  initWeightChart()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  weightChart?.dispose()
  weightChart = null
  clearInterval(refreshInterval)
})
</script>

<style scoped>
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
  font-size: 22px;
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

.three-col {
  grid-template-columns: repeat(3, 1fr);
}

.chart-card {
  display: flex;
  flex-direction: column;
}

.chart-box {
  width: 100%;
  height: 240px;
}

.weight-bars {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.weight-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.weight-icon {
  font-size: 14px;
}

.weight-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary);
}

.weight-value {
  font-size: 14px;
  font-weight: 700;
}

.algo-card {
  display: flex;
  flex-direction: column;
}

.algo-icon {
  font-size: 28px;
  margin-bottom: 12px;
}

.algo-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.algo-principle {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 16px;
}

.algo-params {
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px dashed var(--border-color);
}

.params-title {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.param-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  font-size: 13px;
}

.param-label {
  color: var(--text-secondary);
}

.param-value {
  font-weight: 700;
}

.auto-refresh {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.model-status-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.status-card {
  padding: 20px;
  background: rgba(26, 38, 65, 0.6);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  transition: var(--transition);
}

.status-card:hover {
  border-color: rgba(var(--color-blue-rgb), 0.3);
  background: rgba(26, 38, 65, 0.8);
}

.status-card.running {
  border-color: rgba(var(--color-green-rgb), 0.2);
}

.status-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.status-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.status-icon.poisson {
  background: rgba(var(--color-blue-rgb), 0.12);
}

.status-icon.elo {
  background: rgba(var(--color-gold-rgb), 0.12);
}

.status-icon.monte_carlo {
  background: rgba(var(--color-green-rgb), 0.12);
}

.status-info {
  flex: 1;
}

.status-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.status-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
}

.status-tag.running {
  background: rgba(var(--color-green-rgb), 0.15);
  color: var(--color-green);
}

.status-tag.stopped {
  background: rgba(var(--color-red-rgb), 0.15);
  color: var(--color-red);
}

.status-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
  margin: 0 0 14px 0;
}

.status-params {
  margin-bottom: 12px;
}

.status-data {
  display: flex;
  gap: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color);
}

.data-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.data-label {
  font-size: 11px;
  color: var(--text-muted);
}

.data-value {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.recalc-card .recalc-hint {
  margin: 0 20px 12px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.recalc-card .recalc-result {
  margin: 0 20px 16px;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  background: rgba(var(--color-green-rgb), 0.08);
  border: 1px solid rgba(var(--color-green-rgb), 0.25);
  color: var(--color-green);
  font-size: 13px;
}

.recalc-card .recalc-result.error {
  background: rgba(var(--color-red-rgb), 0.08);
  border-color: rgba(var(--color-red-rgb), 0.3);
  color: var(--color-red);
}

@media (max-width: 1100px) {
  .overview-grid { grid-template-columns: repeat(2, 1fr); }
  .model-status-grid { grid-template-columns: 1fr; }
}
</style>
