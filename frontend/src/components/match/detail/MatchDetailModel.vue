<template>
  <div class="match-detail-model">
    <MatchPredictionCharts
      ref="chartsRef"
      :match="chartMatch"
      :home-short="homeShort"
      :away-short="awayShort"
      :has-xg-lambda="hasXgLambda"
      :matrix-locked="isPredLocked('score_matrix')"
    >
      <template #between>
        <div class="card fusion-meta-card" v-if="match.prediction">
          <div class="card-title">
            <span class="title-bar"></span>
            融合模型细节
          </div>
          <div class="fusion-meta-grid">
            <div class="fusion-meta-item" v-if="match.prediction.primaryScenario">
              <span class="meta-k">主结论场景</span>
              <span class="meta-v">{{ primaryScenarioLabel || match.prediction.primaryScenario }}</span>
            </div>
            <div class="fusion-meta-item">
              <span class="meta-k">模型版本</span>
              <span class="meta-v">{{ match.prediction.modelVersion || '-' }}</span>
            </div>
            <div class="fusion-meta-item">
              <span class="meta-k">权重来源</span>
              <span class="meta-v">
                <UpgradeHint v-if="isPredLocked('weight_source')" inline text="旗舰版解锁" />
                <span v-else class="tag" :class="weightSourceTag(match.prediction.weightSource)">
                  {{ weightSourceText(match.prediction.weightSource) }}
                </span>
              </span>
            </div>
            <div class="fusion-meta-item" v-if="match.prediction.leagueId">
              <span class="meta-k">联赛</span>
              <span class="meta-v">{{ match.prediction.leagueId }}</span>
            </div>
            <div class="fusion-meta-item">
              <span class="meta-k">xG 覆盖</span>
              <span class="meta-v">
                <UpgradeHint v-if="isPredLocked('xg_coverage')" inline text="旗舰版解锁" />
                <template v-else>{{ xgCoverageText(match.prediction.xgCoverage) }}</template>
              </span>
            </div>
            <div class="fusion-meta-item" v-if="match.prediction.xgHome != null">
              <span class="meta-k">xG λ 主 / 客</span>
              <span class="meta-v text-gold">{{ match.prediction.xgHome }} / {{ match.prediction.xgAway }}</span>
            </div>
            <div class="fusion-meta-item" v-if="match.prediction.eloHome != null">
              <span class="meta-k">ELO 主 / 客</span>
              <span class="meta-v">{{ match.prediction.eloHome }} / {{ match.prediction.eloAway }}</span>
            </div>
          </div>
          <div class="weight-used-row" v-if="weightUsedList.length">
            <div class="weight-used-item" v-for="w in weightUsedList" :key="w.key">
              <div class="weight-used-top">
                <span>{{ w.label }}</span>
                <b :style="{ color: w.color }">{{ w.pct }}</b>
              </div>
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: w.pct, background: w.color }"></div>
              </div>
            </div>
          </div>
          <p v-if="isPredLocked('weights_used')" class="empty-hint soft">融合权重明细需旗舰版解锁。</p>
          <p v-else-if="!weightUsedList.length" class="empty-hint soft">旧预测未记录融合权重；点击「重新计算」可写入最新 xG / 分联赛权重。</p>
        </div>
      </template>
    </MatchPredictionCharts>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import MatchPredictionCharts from '@/components/match/MatchPredictionCharts.vue'
import UpgradeHint from '@/components/UpgradeHint.vue'
import { weightSourceTag, xgCoverageText } from './matchDetailFormat'

defineProps({
  match: { type: Object, required: true },
  chartMatch: { type: Object, default: null },
  homeShort: { type: String, default: '' },
  awayShort: { type: String, default: '' },
  hasXgLambda: { type: Boolean, default: false },
  primaryScenarioLabel: { type: String, default: '' },
  weightUsedList: { type: Array, default: () => [] },
  isPredLocked: { type: Function, required: true },
  weightSourceText: { type: Function, required: true },
})

const chartsRef = ref(null)

function refreshCharts() {
  chartsRef.value?.refreshCharts?.()
}

function handleResize() {
  chartsRef.value?.handleResize?.()
}

function disposeCharts() {
  chartsRef.value?.disposeCharts?.()
}

defineExpose({ refreshCharts, handleResize, disposeCharts })
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

.fusion-meta-card {
  margin-bottom: 16px;
}
.fusion-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px 16px;
  margin-bottom: 14px;
}
.fusion-meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fusion-meta-item .meta-k {
  font-size: 11px;
  color: var(--text-muted);
}
.fusion-meta-item .meta-v {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.weight-used-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}
.weight-used-item {
  padding: 8px 10px;
  background: rgba(26, 38, 65, 0.45);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}
.weight-used-top {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.weight-used-top b { font-size: 13px; }
.weight-used-item .progress-bar {
  height: 6px;
  background: rgba(138, 155, 181, 0.15);
  border-radius: 3px;
  overflow: hidden;
}
.weight-used-item .progress-fill {
  height: 100%;
  border-radius: 3px;
}
.empty-hint.soft {
  text-align: left;
  padding: 4px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
