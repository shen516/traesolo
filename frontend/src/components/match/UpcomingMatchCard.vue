<template>
  <div class="match-card card" @click="$emit('detail', match.id)">
    <div class="card-header">
      <div class="league-info">
        <span class="league-icon">
          <MediaImg
            :src="league.logo"
            :fallback="league.icon || '⚽'"
            size="xs"
            :alt="league.name"
          />
        </span>
        <span class="league-name">{{ league.name }}</span>
        <span v-if="match.stage" class="stage-tag" :class="stageTagClass(match.stage)">
          {{ getStageLabel(match.stage) }}
        </span>
      </div>
      <div class="match-time">
        <span class="date">{{ match.date }}</span>
        <span class="time">{{ match.time }}</span>
      </div>
    </div>

    <div class="teams-versus">
      <div class="team home-team">
        <MediaImg
          :src="homeTeam.logo"
          fallback="⚽"
          img-class="team-logo"
          size="sm"
          :alt="homeTeam.name"
        />
        <span class="team-name">{{ homeTeam.short }}</span>
        <span class="team-host">主场</span>
      </div>
      <div class="versus-block">
        <div class="versus">VS</div>
        <div v-if="match.prediction.hasPrediction" class="main-score">{{ match.prediction.mainScore }}</div>
        <div v-else class="score-placeholder">未预测</div>
      </div>
      <div class="team away-team">
        <MediaImg
          :src="awayTeam.logo"
          fallback="⚽"
          img-class="team-logo"
          size="sm"
          :alt="awayTeam.name"
        />
        <span class="team-name">{{ awayTeam.short }}</span>
        <span class="team-host">客场</span>
      </div>
    </div>

    <MatchOddsBrief :match="match" />
    <div v-if="oddsTags.length" class="odds-tags">
      <span
        v-for="t in oddsTags"
        :key="t.key"
        class="tag"
        :class="t.cls"
        :title="t.title"
      >{{ t.text }}</span>
    </div>

    <div v-if="match.prediction.hasPrediction && density === 'full'" class="probability-bars">
      <div class="prob-row">
        <span class="prob-label">主胜</span>
        <div class="prob-bar-wrap">
          <div class="prob-bar home-bar" :style="{ width: (match.prediction.homeWinProb * 100) + '%' }"></div>
        </div>
        <span class="prob-value text-blue">{{ (match.prediction.homeWinProb * 100).toFixed(1) }}%</span>
      </div>
      <div class="prob-row">
        <span class="prob-label">平局</span>
        <div class="prob-bar-wrap">
          <div class="prob-bar draw-bar" :style="{ width: (match.prediction.drawProb * 100) + '%' }"></div>
        </div>
        <span class="prob-value text-orange">{{ (match.prediction.drawProb * 100).toFixed(1) }}%</span>
      </div>
      <div class="prob-row">
        <span class="prob-label">客胜</span>
        <div class="prob-bar-wrap">
          <div class="prob-bar away-bar" :style="{ width: (match.prediction.awayWinProb * 100) + '%' }"></div>
        </div>
        <span class="prob-value text-red">{{ (match.prediction.awayWinProb * 100).toFixed(1) }}%</span>
      </div>
    </div>
    <div v-else-if="!match.prediction.hasPrediction" class="predict-empty">
      <p>还没有本场预测。可一键计算，或进入详情查看完整分析。</p>
    </div>

    <div class="card-footer">
      <template v-if="match.prediction.hasPrediction">
        <div class="tendency">
          <span class="tendency-icon">📌</span>
          {{ match.prediction.tendency }}
        </div>
        <div class="tags-row">
          <span class="tag" :class="confidenceTagClass(match.prediction.confidence)">
            信心{{ levelText(match.prediction.confidence) }}
          </span>
          <template v-if="density === 'full'">
            <span class="tag" :class="riskTagClass(match.prediction.riskLevel)">
              风险{{ levelText(match.prediction.riskLevel) }}
            </span>
            <span class="tag tag-info">总进球 {{ match.prediction.totalGoals }}</span>
            <span
              v-if="match.prediction.primaryScenario"
              class="tag"
              :class="scenarioTagClass(match.prediction.primaryScenario)"
              :title="match.prediction.scenarioLocked ? '用户锁定主结论' : '自动主结论场景'"
            >{{ scenarioShort(match.prediction.primaryScenario) }}{{ match.prediction.scenarioLocked ? '·锁' : '' }}</span>
            <span
              v-if="match.prediction.weightSource"
              class="tag"
              :class="weightSourceTagClass(match.prediction.weightSource)"
            >{{ weightSourceShort(match.prediction.weightSource) }}</span>
            <span v-if="match.prediction.xgCoverage != null" class="tag tag-mid">
              xG {{ Number(match.prediction.xgCoverage) > 0 ? '已用' : '回退' }}
            </span>
          </template>
        </div>
      </template>

      <div class="prediction-actions" @click.stop>
        <button
          v-if="!match.prediction.hasPrediction"
          class="btn btn-primary predict-btn"
          :disabled="predicting || batchRunning"
          @click="$emit('predict', match, false)"
        >
          {{ predicting ? '计算中...' : '计算预测' }}
        </button>
        <template v-else-if="density === 'full'">
          <button
            class="btn btn-outline predict-btn"
            :disabled="predicting || batchRunning"
            @click="$emit('predict', match, true)"
          >
            {{ predicting ? '计算中...' : '重新计算' }}
          </button>
          <button
            class="btn btn-outline predict-btn"
            :disabled="historyLoading"
            @click="$emit('toggle-history', match.id)"
          >
            {{ historyLoading ? '加载中...' : (historyExpanded ? '收起历史' : '历史') }}
          </button>
        </template>
        <button class="btn btn-secondary predict-btn" @click="$emit('detail', match.id)">详情</button>
        <span v-if="errorTip" class="error-tip">{{ errorTip }}</span>
      </div>

      <div v-if="density === 'full' && historyExpanded" class="history-section">
        <div v-if="historyLoading" class="history-loading">
          <span>⏳ 加载中...</span>
        </div>
        <div v-else-if="history?.length > 1" class="history-list">
          <div class="history-title">
            <span class="history-icon">📜</span>
            预测历史记录 ({{ history.length - 1 }}次)
          </div>
          <div
            v-for="(record, index) in history.slice(1)"
            :key="record.id"
            class="history-item"
          >
            <span class="history-index">#{{ history.length - index }}</span>
            <span class="history-score">{{ record.mainScore }}</span>
            <span class="history-tendency">{{ record.tendency }}</span>
            <span class="history-time">{{ formatDateTime(record.created_at) }}</span>
          </div>
        </div>
        <div v-else class="history-empty">暂无历史记录</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatDateTime } from '@/utils/adapters'
import MatchOddsBrief from '@/components/match/MatchOddsBrief.vue'
import {
  getStageLabel,
  stageTagClass,
  confidenceTagClass,
  riskTagClass,
  levelText,
  weightSourceTagClass,
  weightSourceShort,
  scenarioShort,
  scenarioTagClass,
  marketTendencyTagClass,
  deltaLevelTagClass,
} from '@/utils/matchMeta'

const props = defineProps({
  match: { type: Object, required: true },
  league: { type: Object, default: () => ({ name: '未知联赛', icon: '⚽' }) },
  homeTeam: { type: Object, default: () => ({ name: '未知', short: '未知', logo: '⚪' }) },
  awayTeam: { type: Object, default: () => ({ name: '未知', short: '未知', logo: '⚪' }) },
  density: { type: String, default: 'compact' },
  predicting: { type: Boolean, default: false },
  batchRunning: { type: Boolean, default: false },
  errorTip: { type: String, default: '' },
  history: { type: Array, default: null },
  historyExpanded: { type: Boolean, default: false },
  historyLoading: { type: Boolean, default: false },
})

defineEmits(['detail', 'predict', 'toggle-history'])

const oddsTags = computed(() => {
  const a = props.match?.oddsAnalysis
  if (!a) return []
  const tags = []
  if (a.marketTendencyLabel) {
    tags.push({
      key: 'mkt',
      text: `市场${a.marketTendencyLabel}`,
      cls: marketTendencyTagClass(a.marketTendency),
      title: a.overroundPct != null ? `抽水约 ${Number(a.overroundPct).toFixed(1)}%` : '竞彩隐含倾向',
    })
  }
  if (a.deltaLevel && a.maxAbsDeltaPct != null) {
    tags.push({
      key: 'delta',
      text: a.deltaLevel === 'high' ? `偏差大 ${Number(a.maxAbsDeltaPct).toFixed(0)}pt`
        : a.deltaLevel === 'mid' ? `偏差中 ${Number(a.maxAbsDeltaPct).toFixed(0)}pt`
          : `偏差小`,
      cls: deltaLevelTagClass(a.deltaLevel),
      title: a.agreeTendency === false ? '市场与模型倾向不一致' : '市场隐含 vs 模型',
    })
  }
  return tags
})
</script>

<style scoped>
.match-card {
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  position: relative;
  overflow: hidden;
}
.match-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--color-blue), transparent);
  opacity: 0;
  transition: var(--transition);
}
.match-card:hover {
  border-color: rgba(var(--color-blue-rgb), 0.4);
  box-shadow: 0 0 24px rgba(var(--color-blue-rgb), 0.25), 0 4px 20px rgba(0, 0, 0, 0.4);
  transform: translateY(-2px);
}
.match-card:hover::before { opacity: 1; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-color);
}
.league-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
.league-info .league-icon { font-size: 15px; }
.match-time {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
}
.match-time .time {
  color: var(--color-gold);
  font-weight: 600;
}
.teams-versus {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
}
.team {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.team-logo {
  font-size: 28px;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.4));
}
.team-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  text-align: center;
}
.team-host {
  font-size: 10px;
  color: var(--text-muted);
  padding: 1px 6px;
  background: var(--bg-secondary);
  border-radius: 8px;
}
.versus-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.versus {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 700;
  padding: 2px 10px;
  background: var(--bg-secondary);
  border-radius: 4px;
  letter-spacing: 1px;
}
.main-score {
  font-size: 18px;
  font-weight: 800;
  color: var(--color-gold);
  font-family: 'Consolas', 'Microsoft YaHei', sans-serif;
}
.score-placeholder {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
}
.odds-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.predict-empty {
  padding: 10px 12px;
  background: var(--bg-secondary);
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-sm);
}
.predict-empty p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.probability-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
}
.prob-row {
  display: grid;
  grid-template-columns: 36px 1fr 48px;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}
.prob-label {
  color: var(--text-muted);
  font-weight: 600;
}
.prob-bar-wrap {
  height: 6px;
  background: var(--bg-primary);
  border-radius: 3px;
  overflow: hidden;
}
.prob-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
  box-shadow: 0 0 8px currentColor;
}
.home-bar {
  background: linear-gradient(90deg, #0066cc, var(--color-blue));
  color: var(--color-blue);
}
.draw-bar {
  background: linear-gradient(90deg, #b36800, var(--color-orange));
  color: var(--color-orange);
}
.away-bar {
  background: linear-gradient(90deg, #aa1f2c, var(--color-red));
  color: var(--color-red);
}
.prob-value {
  text-align: right;
  font-weight: 700;
  font-size: 11px;
  font-family: 'Consolas', sans-serif;
}
.card-footer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--border-color);
}
.tendency {
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}
.tags-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.stage-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
  margin-left: 4px;
}
.tag-group { background: rgba(var(--color-blue-rgb), 0.15); color: var(--color-blue); border: 1px solid rgba(var(--color-blue-rgb), 0.3); }
.tag-round16 { background: rgba(16, 185, 129, 0.15); color: var(--color-green); border: 1px solid rgba(16, 185, 129, 0.3); }
.tag-quarter { background: rgba(245, 158, 11, 0.15); color: var(--color-orange); border: 1px solid rgba(245, 158, 11, 0.3); }
.tag-semi { background: rgba(236, 72, 153, 0.15); color: var(--color-red); border: 1px solid rgba(236, 72, 153, 0.3); }
.tag-third { background: rgba(251, 191, 36, 0.15); color: var(--color-yellow); border: 1px solid rgba(251, 191, 36, 0.3); }
.tag-final { background: rgba(139, 92, 246, 0.15); color: var(--color-purple); border: 1px solid rgba(139, 92, 246, 0.3); }
.tag-league { background: rgba(148, 163, 184, 0.15); color: var(--text-secondary); border: 1px solid rgba(148, 163, 184, 0.3); }
.prediction-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}
.predict-btn {
  flex-shrink: 0;
  font-size: 12px;
  padding: 6px 12px;
}
.predict-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.error-tip {
  font-size: 10px;
  color: var(--color-red);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-section {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-color);
}
.history-loading {
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
  padding: 8px 0;
}
.history-title {
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-radius: 4px;
  font-size: 11px;
}
.history-index { color: var(--text-muted); min-width: 24px; }
.history-score { color: var(--color-gold); font-weight: 700; }
.history-tendency { flex: 1; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-time { color: var(--text-muted); font-size: 10px; }
.history-empty {
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
  padding: 6px 0;
}
</style>
