<template>
  <div class="card chart-card">
    <div class="card-title">
      <span class="title-bar"></span>
      胜平负概率分布
    </div>
    <div ref="pieChartRef" class="chart-box pie-box"></div>
  </div>

  <div class="card chart-card">
    <div class="card-title">
      <span class="title-bar"></span>
      预期进球数对比
      <span class="card-sub inline-sub">泊松 λ{{ hasXgLambda ? ' · xG λ' : '' }}</span>
    </div>
    <div ref="lambdaChartRef" class="chart-box lambda-box"></div>
  </div>

  <slot name="between" />

  <div class="card chart-card">
    <div class="card-title">
      <span class="title-bar"></span>
      比分概率矩阵热力图
    </div>
    <UpgradeHint
      v-if="matrixLocked"
      text="完整比分矩阵需专业版解锁"
      style="margin:8px 0 12px;"
    />
    <template v-else>
      <div class="heatmap-hint">
        <span>横轴：客队进球数 (0-4)</span>
        <span>纵轴：主队进球数 (0-4)</span>
      </div>
      <div ref="heatmapChartRef" class="chart-box heatmap-box"></div>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useMatchCharts } from '@/composables/useMatchCharts'
import UpgradeHint from '@/components/UpgradeHint.vue'

const props = defineProps({
  /** Match object with prediction (camelCase fields) */
  match: { type: Object, default: null },
  homeShort: { type: String, default: '' },
  awayShort: { type: String, default: '' },
  hasXgLambda: { type: Boolean, default: false },
  matrixLocked: { type: Boolean, default: false },
})

const pieChartRef = ref(null)
const lambdaChartRef = ref(null)
const heatmapChartRef = ref(null)

const { refreshCharts, disposeCharts, handleResize } = useMatchCharts({
  pieChartRef,
  lambdaChartRef,
  heatmapChartRef,
  // Parent MatchDetail owns window resize + dispose lifecycle
  autoBindResize: false,
  getChartContext: () => {
    const m = props.match
    if (!m?.prediction) return null
    return {
      prediction: m.prediction,
      homeShort: props.homeShort,
      awayShort: props.awayShort,
      hasXgLambda: props.hasXgLambda,
    }
  },
})

defineExpose({
  refreshCharts,
  disposeCharts,
  handleResize,
  pieChartRef,
  lambdaChartRef,
  heatmapChartRef,
})
</script>

<style scoped>
.card-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-color);
}

.title-bar {
  display: inline-block;
  width: 3px;
  height: 14px;
  background: linear-gradient(180deg, var(--color-blue), var(--color-gold));
  border-radius: 2px;
}

.chart-card {
  display: flex;
  flex-direction: column;
}

.chart-box {
  width: 100%;
}

.pie-box {
  height: 320px;
}

.lambda-box {
  height: 240px;
}

.inline-sub {
  margin-left: 10px;
  font-size: 12px;
  font-weight: 400;
  color: var(--text-muted);
}

.heatmap-box {
  height: 420px;
}

.heatmap-hint {
  display: flex;
  gap: 24px;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
}
</style>
