<template>
  <div class="match-detail-prediction">
    <div class="card prediction-card">
      <div class="card-title">
        <span class="title-bar"></span>
        预测分析结论
        <span v-if="primaryScenarioLabel" class="scenario-primary-badge tag tag-info">
          主结论 · {{ primaryScenarioLabel }}
        </span>
      </div>

      <div v-if="scenarioList.length" class="scenario-toolbar">
        <button
          v-for="s in scenarioList"
          :key="s.id"
          type="button"
          class="scenario-chip"
          :class="{
            active: viewScenarioId === s.id,
            primary: s.isPrimary,
            muted: s.available === false,
          }"
          :disabled="s.available === false"
          :title="s.available === false ? `不可用：${s.desc || '数据不足'}` : (s.desc || '')"
          @click="$emit('select-scenario', s)"
        >
          <span class="chip-label">{{ s.short || s.label }}</span>
          <span v-if="s.isPrimary" class="chip-flag">主</span>
          <span v-if="match.prediction?.scenarioLocked && s.isPrimary" class="chip-flag lock">锁</span>
        </button>
        <button
          v-if="canLockViewedScenario"
          type="button"
          class="btn btn-outline scenario-lock-btn"
          :disabled="lockingScenario"
          @click="$emit('lock-scenario', true)"
        >
          {{ lockingScenario ? '锁定中...' : '设为主结论并锁定' }}
        </button>
        <button
          v-if="match.prediction?.scenarioLocked"
          type="button"
          class="btn btn-outline scenario-lock-btn"
          :disabled="lockingScenario"
          @click="$emit('lock-scenario', false)"
          title="解除锁定；可把当前浏览场景设为临时主结论"
        >
          {{ lockingScenario ? '处理中...' : '解除锁定' }}
        </button>
      </div>
      <p v-if="scenarioReasonText" class="scenario-reason">{{ scenarioReasonText }}</p>
      <p v-else-if="predictError && !match.prediction?.hasPrediction" class="scenario-reason soft">
        {{ predictError }}
      </p>
      <p v-else-if="!scenarioList.length" class="scenario-reason soft">
        当前预测未含多场景数据，点击「重新计算预测」可写入最新场景结论。
      </p>
      <p v-if="viewingNonPrimary" class="scenario-browse-hint">
        正在浏览「{{ viewScenarioLabel }}」对照结果；本场落库主结论仍为「{{ primaryScenarioLabel }}」。
      </p>

      <UpgradeHint
        v-if="predictionLockedFields.length"
        :text="`已隐藏 ${predictionLockedFields.length} 个深度字段（备选比分/矩阵/关键变量/xG 等），升级专业版或旗舰版解锁`"
        style="margin-bottom:12px;"
      />

      <div class="prediction-grid">
        <div class="prediction-row">
          <span class="pred-label">预测倾向</span>
          <span class="pred-text">{{ displayPrediction.tendency || '暂无' }}</span>
        </div>
        <div class="prediction-row">
          <span class="pred-label">信心等级</span>
          <span class="tag" :class="confidenceTagClass(displayPrediction.confidence)">
            {{ levelText(displayPrediction.confidence) }}
          </span>
        </div>
        <div class="prediction-row">
          <span class="pred-label">风险等级</span>
          <span class="tag" :class="riskTagClass(displayPrediction.riskLevel)">
            {{ levelText(displayPrediction.riskLevel) }}
          </span>
        </div>
        <div class="prediction-row main-score-row">
          <span class="pred-label">主线比分</span>
          <span class="main-score">{{ displayPrediction.mainScore || '-' }}</span>
        </div>
        <div class="prediction-row">
          <span class="pred-label">备选剧本</span>
          <div class="alt-scores">
            <UpgradeHint v-if="isPredLocked('alt_scores')" inline text="升级专业版解锁备选比分" />
            <template v-else>
              <span v-for="score in (displayPrediction.altScores || [])" :key="score" class="tag tag-info alt-score">
                {{ score }}
              </span>
              <span v-if="!(displayPrediction.altScores || []).length" class="pred-text">-</span>
            </template>
          </div>
        </div>
        <div class="prediction-row">
          <span class="pred-label">总进球预测</span>
          <span class="pred-text text-gold pred-text-bold">{{ displayPrediction.totalGoals || '-' }}</span>
        </div>
        <div class="prediction-row key-variables-row">
          <span class="pred-label">关键变量</span>
          <div class="key-variables">
            <UpgradeHint v-if="isPredLocked('key_variables')" inline text="升级专业版解锁关键变量" />
            <template v-else>
              <span v-for="(v, idx) in (displayPrediction.keyVariables || [])" :key="v" class="variable-tag">
                <span class="var-index">{{ idx + 1 }}</span>
                {{ v }}
              </span>
              <span v-if="!(displayPrediction.keyVariables || []).length" class="pred-text">-</span>
            </template>
          </div>
        </div>
        <div class="prediction-row scenario-prob-row" v-if="displayPrediction.homeWinProb != null">
          <span class="pred-label">胜平负</span>
          <div class="scenario-probs">
            <span>主 {{ (displayPrediction.homeWinProb * 100).toFixed(1) }}%</span>
            <span>平 {{ (displayPrediction.drawProb * 100).toFixed(1) }}%</span>
            <span>客 {{ (displayPrediction.awayWinProb * 100).toFixed(1) }}%</span>
          </div>
        </div>
      </div>
    </div>

    <div class="card analysis-card">
      <div class="card-title">
        <span class="title-bar"></span>
        简要分析
      </div>
      <UpgradeHint
        v-if="isPredLocked('analysis')"
        text="分析文案需专业版解锁"
      />
      <p v-else class="analysis-text">{{ displayPrediction.analysis || '暂无分析文案，请点击「重新计算预测」。' }}</p>
    </div>
  </div>
</template>

<script setup>
import UpgradeHint from '@/components/UpgradeHint.vue'
import {
  levelText,
  confidenceTagClass,
  riskTagClass,
} from './matchDetailFormat'

defineProps({
  match: { type: Object, required: true },
  displayPrediction: { type: Object, required: true },
  scenarioList: { type: Array, default: () => [] },
  primaryScenarioLabel: { type: String, default: '' },
  viewScenarioLabel: { type: String, default: '' },
  scenarioReasonText: { type: String, default: '' },
  viewingNonPrimary: { type: Boolean, default: false },
  canLockViewedScenario: { type: Boolean, default: false },
  lockingScenario: { type: Boolean, default: false },
  viewScenarioId: { type: String, default: '' },
  predictionLockedFields: { type: Array, default: () => [] },
  predictError: { type: String, default: '' },
  isPredLocked: { type: Function, required: true },
})

defineEmits(['select-scenario', 'lock-scenario'])
</script>

<style scoped>
.match-detail-prediction {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
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

.prediction-card {
  display: flex;
  flex-direction: column;
}

.prediction-card .card-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.scenario-primary-badge {
  margin-left: auto;
  font-size: 12px;
  font-weight: 600;
}

.scenario-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 10px;
}

.scenario-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}

.scenario-chip:hover {
  border-color: var(--color-gold);
  color: var(--text-primary);
}

.scenario-chip.active {
  border-color: var(--color-gold);
  color: var(--color-gold);
  background: rgba(var(--color-gold-rgb), 0.08);
}

.scenario-chip.primary:not(.active) {
  border-color: rgba(var(--color-blue-rgb), 0.45);
}

.scenario-chip:disabled,
.scenario-chip.muted {
  opacity: 0.45;
  cursor: not-allowed;
}

.chip-flag.lock {
  background: rgba(var(--color-orange-rgb), 0.25);
  color: var(--color-orange);
}

.scenario-lock-btn {
  margin-left: 4px;
  font-size: 12px;
  padding: 6px 10px;
}

.chip-flag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(var(--color-blue-rgb), 0.2);
  color: var(--color-blue);
}

.scenario-reason,
.scenario-browse-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0 0 12px;
  line-height: 1.5;
}

.scenario-browse-hint {
  color: var(--color-orange);
}

.scenario-prob-row .scenario-probs {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.prediction-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.prediction-row {
  display: grid;
  grid-template-columns: 100px 1fr;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}

.pred-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
}

.pred-text {
  font-size: 14px;
  color: var(--text-primary);
}

.pred-text-bold {
  font-weight: 700;
}

.main-score-row {
  background: linear-gradient(135deg, rgba(var(--color-gold-rgb), 0.08), rgba(var(--color-blue-rgb), 0.05));
  border-color: rgba(var(--color-gold-rgb), 0.3);
}

.main-score {
  font-size: 36px;
  font-weight: 800;
  color: var(--color-gold);
  font-family: 'Consolas', 'Microsoft YaHei', sans-serif;
  letter-spacing: 2px;
  text-shadow: 0 0 20px rgba(var(--color-gold-rgb), 0.4);
}

.alt-scores {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.alt-score {
  font-family: 'Consolas', monospace;
  font-weight: 700;
}

.key-variables-row {
  grid-template-columns: 100px 1fr;
  align-items: flex-start;
}

.key-variables {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.variable-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(var(--color-blue-rgb), 0.08);
  border: 1px solid rgba(var(--color-blue-rgb), 0.3);
  border-radius: 12px;
  font-size: 12px;
  color: var(--color-blue);
}

.var-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  background: var(--color-blue);
  color: var(--bg-primary);
  border-radius: 50%;
  font-size: 10px;
  font-weight: 800;
}

.analysis-text {
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-secondary);
  text-indent: 2em;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--color-blue);
}
</style>
