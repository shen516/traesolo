<template>
  <div class="model-monitor-tab">
    <div class="card chart-card">
      <div class="card-header">
        <h2 class="card-title">模型准确率趋势</h2>
        <span class="card-sub">近 {{ accuracyTrend.length }} 天</span>
      </div>
      <div ref="trendChartRef" class="chart-box large"></div>
    </div>

    <div class="card monitor-card">
      <div class="card-header">
        <h2 class="card-title">模型监控</h2>
        <div class="card-actions">
          <select v-model.number="monitorDays" class="monitor-select" @change="fetchMonitor">
            <option :value="30">近 30 天</option>
            <option :value="60">近 60 天</option>
            <option :value="90">近 90 天</option>
          </select>
          <button class="refresh-btn" @click="fetchMonitor" :disabled="monitorLoading">
            {{ monitorLoading ? '加载中...' : '刷新' }}
          </button>
        </div>
      </div>

      <div v-if="monitorError" class="quality-error" style="margin: 0 20px 12px">{{ monitorError }}</div>

      <div v-if="monitorDrift" class="monitor-body">
        <div class="monitor-kpis">
          <div class="monitor-kpi" :class="driftStatusClass(monitorDrift.status)">
            <span class="qk-label">漂移状态</span>
            <b>{{ driftStatusText(monitorDrift.status) }}</b>
            <span class="qk-sub" v-if="monitorDrift.drift != null">
              较基线 {{ formatDrift(monitorDrift.drift) }}
            </span>
          </div>
          <div class="monitor-kpi">
            <span class="qk-label">近期准确率</span>
            <b>{{ formatMetricPct(monitorDrift.recent_accuracy) }}</b>
            <span class="qk-sub">样本 {{ monitorDrift.recent_sample ?? '-' }}</span>
          </div>
          <div class="monitor-kpi">
            <span class="qk-label">基线准确率</span>
            <b>{{ formatMetricPct(monitorDrift.baseline_accuracy) }}</b>
            <span class="qk-sub">趋势点 {{ monitorDrift.baseline_points ?? 0 }}</span>
          </div>
          <div class="monitor-kpi">
            <span class="qk-label">Brier</span>
            <b>{{ formatMetricNum(monitorDrift.recent_brier) }}</b>
            <span class="qk-sub">越低越好</span>
          </div>
          <div class="monitor-kpi">
            <span class="qk-label">校准 ECE</span>
            <b>{{ formatMetricNum(monitorDrift.recent_ece) }}</b>
            <span class="qk-sub">越低越好</span>
          </div>
        </div>

        <div class="monitor-chart-wrap" v-if="monitorCalibration?.calibration_bins?.length">
          <div class="monitor-chart-head">
            <span class="card-sub">
              校准分箱（置信度 vs 实际命中）
              · 全样本准确率 {{ formatMetricPct(monitorCalibration.accuracy) }}
              · Brier {{ formatMetricNum(monitorCalibration.brier) }}
            </span>
          </div>
          <div ref="calibrationChartRef" class="chart-box large"></div>
        </div>
        <p v-else-if="!monitorLoading" class="empty-hint">暂无校准数据（需有已完赛且已预测场次）</p>
      </div>
      <p v-else-if="monitorLoading" class="empty-hint">监控数据加载中…</p>
    </div>

    <div class="card monitor-card" style="margin-top: 16px">
      <div class="card-header">
        <h2 class="card-title">竞彩隐含 vs 模型</h2>
        <span class="card-sub">SP 归一化隐含概率与赛前预测对照（分析用，非投注建议）</span>
      </div>
      <div v-if="monitorOddsDeviation" class="monitor-body">
        <div class="monitor-kpis">
          <div class="monitor-kpi">
            <span class="qk-label">有 SP 样本</span>
            <b>{{ monitorOddsDeviation.sample_size ?? 0 }}</b>
            <span class="qk-sub">近 {{ monitorOddsDeviation.days }} 天完赛</span>
          </div>
          <div class="monitor-kpi">
            <span class="qk-label">可对照预测</span>
            <b>{{ monitorOddsDeviation.with_prediction ?? 0 }}</b>
            <span class="qk-sub">同时有赛前预测</span>
          </div>
          <div class="monitor-kpi">
            <span class="qk-label">平均抽水</span>
            <b>{{ monitorOddsDeviation.avg_overround_pct != null ? monitorOddsDeviation.avg_overround_pct + '%' : '-' }}</b>
            <span class="qk-sub">overround</span>
          </div>
          <div class="monitor-kpi">
            <span class="qk-label">平均最大偏差</span>
            <b>{{ monitorOddsDeviation.avg_max_abs_delta_pct != null ? monitorOddsDeviation.avg_max_abs_delta_pct + 'pt' : '-' }}</b>
            <span class="qk-sub">|市场−模型|</span>
          </div>
          <div class="monitor-kpi">
            <span class="qk-label">倾向一致率</span>
            <b>{{ formatMetricPct(monitorOddsDeviation.agree_rate) }}</b>
            <span class="qk-sub">
              低/中/高偏差
              {{ monitorOddsDeviation.by_level?.low ?? 0 }}/{{ monitorOddsDeviation.by_level?.mid ?? 0 }}/{{ monitorOddsDeviation.by_level?.high ?? 0 }}
            </span>
          </div>
        </div>
        <p class="empty-hint" style="margin: 8px 20px 16px">
          {{ monitorOddsDeviation.disclaimer || '正偏差 = 市场隐含高于模型。' }}
          <template v-if="monitorOddsDeviation.mean_delta">
            均值差：主 {{ ((monitorOddsDeviation.mean_delta.home || 0) * 100).toFixed(1) }}pt
            · 平 {{ ((monitorOddsDeviation.mean_delta.draw || 0) * 100).toFixed(1) }}pt
            · 客 {{ ((monitorOddsDeviation.mean_delta.away || 0) * 100).toFixed(1) }}pt
          </template>
        </p>
      </div>
      <p v-else-if="!monitorLoading" class="empty-hint">暂无赔率对照样本（需竞彩 SP + 完赛预测）</p>
    </div>

    <ScoreTop3BacktestCard :active="isMonitorActive" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import echarts from '@/utils/echarts'
import { CHART_COLORS, MODEL_COLORS } from '@/utils/chartTheme'
import { modelApi, trendApi } from '@/api'
import ScoreTop3BacktestCard from '@/components/jingcai/ScoreTop3BacktestCard.vue'
import {
  driftStatusText,
  driftStatusClass,
  formatMetricPct,
  formatMetricNum,
  formatDrift,
  formatTrendDate,
} from './modelFormatters'

const route = useRoute()
const isMonitorActive = computed(() => route.params.tab === 'monitor')

const trendChartRef = ref(null)
const calibrationChartRef = ref(null)
let trendChart = null
let calibrationChart = null

const monitorDays = ref(30)
const monitorDrift = ref(null)
const monitorCalibration = ref(null)
const monitorOddsDeviation = ref(null)
const monitorLoading = ref(false)
const monitorError = ref(null)
const accuracyTrend = ref([])

function initTrendChart() {
  if (!trendChartRef.value) return
  if (!trendChart) trendChart = echarts.init(trendChartRef.value)
  const accValues = accuracyTrend.value.map(i => Number(i.accuracy)).filter(n => !Number.isNaN(n))
  const yMin = accValues.length ? Math.max(0, Math.floor(Math.min(...accValues) - 5)) : 40
  const yMax = accValues.length ? Math.min(100, Math.ceil(Math.max(...accValues) + 5)) : 80
  trendChart.setOption({
    tooltip: { trigger: 'axis', formatter: params => `${params[0].axisValue}<br/>准确率: <b>${params[0].data}%</b>` },
    grid: { left: 44, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: accuracyTrend.value.map(i => i.date),
      axisLine: { lineStyle: { color: CHART_COLORS.border } },
      axisTick: { show: false },
      axisLabel: { color: CHART_COLORS.textMuted, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      min: yMin,
      max: yMax,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: CHART_COLORS.textMuted, fontSize: 11, formatter: '{value}%' },
      splitLine: { lineStyle: { color: CHART_COLORS.border, type: 'dashed' } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        data: accuracyTrend.value.map(i => Number(i.accuracy)),
        lineStyle: { color: MODEL_COLORS.monte_carlo, width: 2 },
        itemStyle: { color: MODEL_COLORS.monte_carlo, borderColor: CHART_COLORS.bgPrimary, borderWidth: 2 },
        symbol: 'circle',
        symbolSize: 6,
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(61, 255, 154, 0.45)' },
            { offset: 1, color: 'rgba(61, 255, 154, 0)' },
          ]),
        },
      },
    ],
  })
}

function initCalibrationChart() {
  if (!calibrationChartRef.value || !monitorCalibration.value) return
  if (!calibrationChart) calibrationChart = echarts.init(calibrationChartRef.value)
  const bins = monitorCalibration.value.calibration_bins || []
  const n = bins.length || 5
  const labels = bins.map((_, i) => `${Math.round(((i + 0.5) / n) * 100)}%`)
  const conf = bins.map(b => (b.avg_confidence != null ? +(b.avg_confidence * 100).toFixed(1) : null))
  const acc = bins.map(b => (b.avg_accuracy != null ? +(b.avg_accuracy * 100).toFixed(1) : null))
  calibrationChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const lines = [params[0]?.axisValue || '']
        for (const p of params) {
          if (p.data != null) lines.push(`${p.marker}${p.seriesName}: <b>${p.data}%</b>`)
        }
        return lines.join('<br/>')
      },
    },
    legend: { data: ['平均置信度', '实际命中率'], bottom: 0, textStyle: { color: CHART_COLORS.textMuted, fontSize: 12 } },
    grid: { left: 44, right: 20, top: 20, bottom: 44 },
    xAxis: {
      type: 'category',
      data: labels,
      name: '置信度分箱',
      nameTextStyle: { color: CHART_COLORS.textMuted, fontSize: 11 },
      axisLine: { lineStyle: { color: CHART_COLORS.border } },
      axisLabel: { color: CHART_COLORS.textMuted, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: { color: CHART_COLORS.textMuted, fontSize: 11, formatter: '{value}%' },
      splitLine: { lineStyle: { color: CHART_COLORS.border, type: 'dashed' } },
    },
    series: [
      { name: '平均置信度', type: 'bar', data: conf, itemStyle: { color: MODEL_COLORS.poisson }, barGap: '10%' },
      { name: '实际命中率', type: 'bar', data: acc, itemStyle: { color: MODEL_COLORS.monte_carlo } },
    ],
  })
}

async function fetchMonitor() {
  monitorLoading.value = true
  monitorError.value = null
  try {
    const [drift, cal, oddsDev] = await Promise.all([
      modelApi.getMonitorDrift({ days: monitorDays.value }),
      modelApi.getMonitorCalibration({ days: monitorDays.value }),
      modelApi.getMonitorOddsDeviation({ days: monitorDays.value }),
    ])
    monitorDrift.value = drift
    monitorCalibration.value = cal
    monitorOddsDeviation.value = oddsDev
    await nextTick()
    initCalibrationChart()
  } catch (e) {
    monitorError.value = e?.message || '模型监控加载失败'
  } finally {
    monitorLoading.value = false
  }
}

async function loadMonitorTab() {
  try {
    const trendsRes = await trendApi.getRecent(30)
    const trends = trendsRes?.trends || trendsRes || []
    accuracyTrend.value = trends.map(t => ({
      ...t,
      date: formatTrendDate(t.date),
      accuracy: Number(t.accuracy),
    }))
    await fetchMonitor()
    await nextTick()
    initTrendChart()
    if (monitorCalibration.value?.calibration_bins?.length) {
      initCalibrationChart()
    }
  } catch (e) {
    monitorError.value = e?.message || '监控数据加载失败'
  }
}

function handleResize() {
  trendChart?.resize()
  calibrationChart?.resize()
}

onMounted(() => {
  loadMonitorTab()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  calibrationChart?.dispose()
  trendChart = null
  calibrationChart = null
})
</script>

<style scoped>
.chart-card {
  display: flex;
  flex-direction: column;
}
.chart-box {
  width: 100%;
  height: 240px;
}
.chart-box.large {
  height: 340px;
}
.quality-error {
  margin: 0 20px 12px;
  color: var(--color-red);
  font-size: 13px;
}
.monitor-select {
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.monitor-body {
  padding: 0 20px 16px;
}
.monitor-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.monitor-kpi {
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.monitor-kpi b {
  font-size: 20px;
  color: var(--color-gold);
  font-weight: 600;
}
.monitor-kpi .qk-label {
  font-size: 12px;
  color: var(--text-secondary);
}
.monitor-kpi .qk-sub {
  font-size: 11px;
  color: var(--text-muted, var(--text-secondary));
}
.monitor-kpi.status-stable b { color: var(--color-blue); }
.monitor-kpi.status-improved b { color: var(--color-green); }
.monitor-kpi.status-degraded {
  border-color: rgba(var(--color-red-rgb), 0.45);
  background: rgba(var(--color-red-rgb), 0.08);
}
.monitor-kpi.status-degraded b { color: var(--color-red); }
.monitor-chart-wrap {
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}
.monitor-chart-head {
  margin-bottom: 8px;
}
</style>
