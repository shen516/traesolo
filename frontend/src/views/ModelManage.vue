<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">模型管理</h1>
      <p class="page-subtitle">集成多模型的预测引擎，持续优化预测精度</p>
    </div>

    <PageTabs :model-value="activeTab" route-base="/model" :tabs="modelTabs" />

    <div v-if="overviewLoading && activeTab === 'overview'" class="state-banner loading-banner">
      <span class="spinner"></span>
      <span>数据加载中...</span>
    </div>

    <div v-if="isTraining" class="state-banner training-banner">
      <span class="spinner"></span>
      <span>{{ trainingMessage }}</span>
      <div class="training-progress">
        <div class="training-bar">
          <div class="training-fill" :style="{ width: trainingProgress + '%' }"></div>
        </div>
        <span class="training-percent">{{ trainingProgress }}%</span>
      </div>
    </div>

    <div v-if="p0Pipeline.running" class="state-banner training-banner">
      <span class="spinner"></span>
      <span>{{ p0Pipeline.message || p0PhaseLabel }}</span>
    </div>

    <div v-if="overviewError && activeTab === 'overview'" class="state-banner error-banner">
      <span>⚠️ {{ overviewError }}</span>
      <button class="retry-btn" @click="fetchOverviewData">重试</button>
    </div>

    <!-- 只挂载路由对应的 tab，外层 KeepAlive 缓存；切回由 onActivated 恢复图表/轮询，页面卸载时各 tab 清理兜底仍执行 -->
    <KeepAlive>
      <component :is="currentTabComponent" />
    </KeepAlive>
  </div>
</template>

<script setup>
/**
 * 模型管理壳：只负责路由 tab、全局横幅与生命周期挂载。
 * 各 tab 自包含；跨 tab 状态在 modelStore（训练轮询 / P0 / qualityData 徽章）。
 */
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import PageTabs from '@/components/common/PageTabs.vue'
import {
  attachRunningP0,
  attachRunningTraining,
  fetchOverviewData,
  isTraining,
  overviewError,
  overviewLoading,
  p0PhaseLabel,
  p0Pipeline,
  qualityBadge,
  stopAllPolling,
  trainingMessage,
  trainingProgress,
} from './model/modelStore'

const ModelOverviewTab = defineAsyncComponent(() => import('./model/ModelOverviewTab.vue'))
const ModelTrainingTab = defineAsyncComponent(() => import('./model/ModelTrainingTab.vue'))
const ModelQualityTab = defineAsyncComponent(() => import('./model/ModelQualityTab.vue'))
const ModelMonitorTab = defineAsyncComponent(() => import('./model/ModelMonitorTab.vue'))

const route = useRoute()
const MODEL_TABS = new Set(['overview', 'training', 'quality', 'monitor'])
const activeTab = computed(() => {
  const t = route.params.tab
  return MODEL_TABS.has(t) ? t : 'overview'
})

// tab 组件映射（保留上方懒加载分包）；路由变化驱动挂载组件自动切换，无需额外 watch
const tabComponents = {
  overview: ModelOverviewTab,
  training: ModelTrainingTab,
  quality: ModelQualityTab,
  monitor: ModelMonitorTab,
}
const currentTabComponent = computed(() => tabComponents[activeTab.value])

const modelTabs = computed(() => [
  { key: 'overview', label: '概览' },
  { key: 'training', label: '训练记录' },
  { key: 'quality', label: '数据质量', badge: qualityBadge.value },
  { key: 'monitor', label: '监控诊断' },
])

onMounted(() => {
  attachRunningTraining()
  attachRunningP0()
})

onBeforeUnmount(() => {
  stopAllPolling()
})
</script>

<style scoped>
.training-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}
.training-bar {
  width: 120px;
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.12);
  overflow: hidden;
}
.training-fill {
  height: 100%;
  background: var(--color-green);
  transition: width 0.4s ease;
}
.training-percent {
  font-size: 12px;
  color: var(--text-muted);
  min-width: 36px;
}
</style>
