<template>
  <div class="match-detail-header">
    <div class="page-header">
      <button class="back-btn" @click="$emit('back')">
        <span class="back-icon">←</span>
        <span>返回列表</span>
      </button>
      <div class="page-title">
        <span class="title-text">赛事分析详情</span>
        <span class="match-id">#{{ match.id }}</span>
      </div>
      <div class="header-actions">
        <button
          class="export-btn recalc-btn"
          :disabled="recalculating || loading"
          @click="$emit('recalculate')"
        >
          {{ recalculating ? '计算中...' : '重新计算预测' }}
        </button>
        <button class="export-btn" @click="$emit('export')">
          <span class="export-icon">📥</span>
          <span>导出文本报告</span>
        </button>
      </div>
    </div>
    <div v-if="predictError" class="state-banner error-banner">{{ predictError }}</div>

    <div class="info-card card">
      <div class="league-badge">
        <span class="league-icon">
          <MediaImg
            :src="league.logo"
            :fallback="league.icon || '⚽'"
            size="xs"
            :alt="league.name"
          />
        </span>
        <span class="league-name">{{ league.name }}</span>
        <span class="status-tag tag" :class="statusClass(match.status)">
          {{ statusText(match.status) }}
        </span>
      </div>
      <div class="teams-display">
        <div class="team-side home">
          <MediaImg
            :src="homeTeam.logo"
            fallback="⚽"
            img-class="team-logo"
            size="lg"
            :alt="homeTeam.name"
          />
          <span class="team-name">{{ homeTeam.name }}</span>
          <span class="team-tag">主队</span>
        </div>
        <div class="vs-block">
          <div class="vs-text" v-if="match.status === 'finished' && match.homeGoals != null">
            {{ match.homeGoals }} - {{ match.awayGoals }}
          </div>
          <div class="vs-text" v-else>VS</div>
          <div class="match-time">{{ match.date || '-' }}</div>
          <div class="match-time-bold">{{ match.time || '--:--' }}</div>
          <div v-if="match.round || match.stage" class="match-round">
            {{ match.round || stageText(match.stage) }}
          </div>
        </div>
        <div class="team-side away">
          <MediaImg
            :src="awayTeam.logo"
            fallback="⚽"
            img-class="team-logo"
            size="lg"
            :alt="awayTeam.name"
          />
          <span class="team-name">{{ awayTeam.name }}</span>
          <span class="team-tag">客队</span>
        </div>
      </div>
      <div class="match-meta">
        <div class="meta-item">
          <span class="meta-icon">🏟️</span>
          <div class="meta-content">
            <span class="meta-label">场地</span>
            <span class="meta-value">{{ match.venue || '待定' }}</span>
          </div>
        </div>
        <div class="meta-item">
          <span class="meta-icon">🌤️</span>
          <div class="meta-content">
            <span class="meta-label">天气</span>
            <span class="meta-value">{{ match.weather || '暂无数据' }}</span>
          </div>
        </div>
        <div class="meta-item">
          <span class="meta-icon">🌡️</span>
          <div class="meta-content">
            <span class="meta-label">温度</span>
            <span class="meta-value">{{ match.temperature || '暂无数据' }}</span>
          </div>
        </div>
        <div class="meta-item">
          <span class="meta-icon">🌾</span>
          <div class="meta-content">
            <span class="meta-label">草坪</span>
            <span class="meta-value">{{ match.pitch || '暂无数据' }}</span>
          </div>
        </div>
      </div>

      <div class="odds-panel">
        <div class="odds-panel-head">
          <span class="odds-panel-title">竞彩参考</span>
          <span class="odds-panel-note">仅供分析，不构成投注建议</span>
        </div>
        <template v-if="hasAnyOdds">
          <div class="odds-grid">
            <div class="odds-cell">
              <span class="odds-k">胜平负 SP</span>
              <span class="odds-v">
                胜 {{ fmtOdds(match.oddsNspfWin) }}
                · 平 {{ fmtOdds(match.oddsNspfDraw) }}
                · 负 {{ fmtOdds(match.oddsNspfLose) }}
              </span>
            </div>
            <div class="odds-cell">
              <span class="odds-k">让球 {{ handicapLabel || '-' }} SP</span>
              <span class="odds-v">
                胜 {{ fmtOdds(match.oddsSpfWin) }}
                · 平 {{ fmtOdds(match.oddsSpfDraw) }}
                · 负 {{ fmtOdds(match.oddsSpfLose) }}
              </span>
            </div>
          </div>
          <div v-if="!hasNspf" class="odds-gate-hint">
            胜平负未开售或 SP 不完整：盘口对照暂不可用，不影响模型预测计算。
          </div>
          <div v-if="oddsAnalysisView" class="odds-implied-block">
            <div class="odds-implied-row">
              <span class="odds-k">隐含概率（归一化）</span>
              <span class="odds-v">
                主 {{ pct1(oddsAnalysisView.impliedHome ?? oddsAnalysisView.nspf?.home) }}
                · 平 {{ pct1(oddsAnalysisView.impliedDraw ?? oddsAnalysisView.nspf?.draw) }}
                · 客 {{ pct1(oddsAnalysisView.impliedAway ?? oddsAnalysisView.nspf?.away) }}
              </span>
            </div>
            <div class="odds-implied-row">
              <span class="odds-k">市场倾向 / 抽水</span>
              <span class="odds-v">
                {{ oddsAnalysisView.marketTendencyLabel || '-' }}
                · overround
                {{ oddsAnalysisView.overroundPct != null ? Number(oddsAnalysisView.overroundPct).toFixed(1) + '%' : '-' }}
              </span>
            </div>
            <div v-if="oddsAnalysisView.vsModel" class="odds-implied-row">
              <span class="odds-k">相对模型（市场−模型）</span>
              <span class="odds-v">
                主 {{ pctPoints((oddsAnalysisView.vsModel.deltaHome || 0) * 100) }}
                · 平 {{ pctPoints((oddsAnalysisView.vsModel.deltaDraw || 0) * 100) }}
                · 客 {{ pctPoints((oddsAnalysisView.vsModel.deltaAway || 0) * 100) }}
                · 最大 {{ Number(oddsAnalysisView.vsModel.maxAbsDeltaPct || 0).toFixed(1) }}pt
                （{{ oddsAnalysisView.vsModel.agreeTendency ? '倾向一致' : '倾向不一致' }}）
              </span>
            </div>
          </div>
          <div v-if="heuristicsView" class="odds-heuristic-block">
            <div class="odds-heuristic-head">
              <span class="odds-k">看盘启发式对照</span>
              <span class="odds-panel-note">{{ heuristicsView.disclaimer }}</span>
            </div>
            <div class="odds-implied-row" v-if="heuristicsView.leanLabel">
              <span class="odds-k">胜平负倾向</span>
              <span class="odds-v">{{ heuristicsView.leanLabel }}
                <template v-if="heuristicsView.mainScore">
                  · 主推 {{ heuristicsView.mainScore }}
                  <template v-if="(heuristicsView.altScores || []).length">
                    · 备选 {{ heuristicsView.altScores.join(' / ') }}
                  </template>
                </template>
              </span>
            </div>
            <div class="odds-implied-row" v-if="heuristicsView.handicapLeanLabel">
              <span class="odds-k">让球倾向</span>
              <span class="odds-v">{{ heuristicsView.handicapLeanLabel }}</span>
            </div>
            <div class="odds-implied-row" v-if="heuristicsView.totalGoals">
              <span class="odds-k">进球数（由比分）</span>
              <span class="odds-v">{{ heuristicsView.totalGoals.band }}（合计 {{ heuristicsView.totalGoals.total }}）</span>
            </div>
            <div class="odds-implied-row" v-if="heuristicsView.htft?.combos?.length">
              <span class="odds-k">半全场（由比分）</span>
              <span class="odds-v">{{ heuristicsView.htft.combos.join(' / ') }}</span>
            </div>
            <div class="odds-heuristic-rules" v-if="(heuristicsView.rulesHit || []).length">
              <div v-for="(r, i) in heuristicsView.rulesHit" :key="i" class="odds-rule-line">{{ r }}</div>
            </div>
          </div>
        </template>
        <p v-else class="odds-empty">
          暂无竞彩赔率。需「竞彩列表」采集覆盖本场后才会写入让球与胜平负；模型预测不受开售状态影响。
        </p>
      </div>
    </div>

    <div class="injury-banner" v-if="injuryAlerts.length">
      <div class="injury-banner-title">临场伤病提示（分析用，非投注建议）</div>
      <div class="injury-item" v-for="a in injuryAlerts" :key="a.id || a.description">
        <span class="tag" :class="riskTagClass(a.level)">{{ levelText(a.level) }}</span>
        <UpgradeHint
          v-if="isAlertLocked(a)"
          inline
          text="升级旗舰版查看风控详情"
        />
        <span v-else class="injury-desc">{{ a.description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import UpgradeHint from '@/components/UpgradeHint.vue'
import { fmtOdds, pct1, pctPoints } from '@/utils/matchMeta'
import {
  stageText,
  statusClass,
  statusText,
  levelText,
  riskTagClass,
  isAlertLocked,
} from './matchDetailFormat'

defineProps({
  match: { type: Object, required: true },
  homeTeam: { type: Object, required: true },
  awayTeam: { type: Object, required: true },
  league: { type: Object, required: true },
  hasAnyOdds: { type: Boolean, default: false },
  hasNspf: { type: Boolean, default: false },
  handicapLabel: { type: [String, Number], default: '' },
  oddsAnalysisView: { type: Object, default: null },
  heuristicsView: { type: Object, default: null },
  injuryAlerts: { type: Array, default: () => [] },
  recalculating: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  predictError: { type: String, default: '' },
})

defineEmits(['back', 'recalculate', 'export'])
</script>

<style scoped>
.match-detail-header {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  gap: 12px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.recalc-btn {
  background: var(--bg-card);
  border-color: var(--border-color);
  color: var(--text-primary);
}
.recalc-btn:hover:not(:disabled) {
  border-color: var(--color-blue);
  color: var(--color-blue);
  background: rgba(var(--color-blue-rgb), 0.08);
  box-shadow: none;
}
.error-banner {
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  background: rgba(var(--color-red-rgb), 0.12);
  border: 1px solid rgba(var(--color-red-rgb), 0.35);
  color: var(--color-red);
  font-size: 13px;
  margin-bottom: 8px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition);
  font-size: 13px;
}

.back-btn:hover {
  border-color: var(--color-blue);
  color: var(--color-blue);
  box-shadow: 0 0 12px rgba(var(--color-blue-rgb), 0.2);
}

.back-icon {
  font-size: 16px;
  font-weight: 700;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.match-id {
  font-size: 12px;
  color: var(--text-muted);
  padding: 2px 8px;
  background: var(--bg-card);
  border-radius: 4px;
  font-family: 'Consolas', monospace;
}

.export-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  background: linear-gradient(135deg, #0066cc, #004499);
  border: 1px solid #0066cc;
  border-radius: var(--radius-sm);
  color: #fff;
  cursor: pointer;
  transition: var(--transition);
  font-size: 13px;
  font-weight: 600;
}

.export-btn:hover {
  background: linear-gradient(135deg, #0077dd, #0055aa);
  box-shadow: 0 0 16px rgba(var(--color-blue-rgb), 0.4);
}

.export-icon {
  font-size: 14px;
}

.info-card {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.league-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
}

.league-icon {
  font-size: 18px;
}

.league-name {
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 600;
}

.status-tag {
  margin-left: auto;
  text-transform: capitalize;
}

.teams-display {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 24px;
  padding: 20px 0;
}

.team-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.team-side :deep(.team-logo) {
  font-size: 48px;
  filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.5));
}

.team-side .team-name {
  font-size: 22px;
  font-weight: 800;
  color: var(--text-primary);
  text-align: center;
  letter-spacing: 1px;
}

.team-tag {
  font-size: 11px;
  color: var(--text-muted);
  padding: 2px 10px;
  background: var(--bg-secondary);
  border-radius: 10px;
  border: 1px solid var(--border-color);
}

.vs-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.vs-text {
  font-size: 18px;
  font-weight: 800;
  color: var(--color-gold);
  letter-spacing: 2px;
}

.match-time {
  font-size: 12px;
  color: var(--text-muted);
}

.match-time-bold {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: 'Consolas', monospace;
}

.match-round {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.match-meta {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.injury-banner {
  padding: 14px 16px;
  background: rgba(var(--color-orange-rgb), 0.08);
  border: 1px solid rgba(var(--color-orange-rgb), 0.25);
  border-radius: var(--radius-md);
}

.injury-banner-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-orange);
  margin-bottom: 8px;
}

.injury-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.odds-panel {
  margin-top: 14px;
  padding: 12px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.odds-panel-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.odds-panel-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-gold);
}

.odds-panel-note {
  font-size: 11px;
  color: var(--text-muted);
}

.odds-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.odds-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.odds-k {
  font-size: 11px;
  color: var(--text-muted);
}

.odds-v {
  font-size: 13px;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.odds-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}

.odds-implied-block {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.odds-gate-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-gold, #c9a227);
  line-height: 1.45;
}

.odds-heuristic-block {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.odds-heuristic-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 2px;
}

.odds-heuristic-rules {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.odds-rule-line {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.odds-implied-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

@media (max-width: 720px) {
  .odds-grid {
    grid-template-columns: 1fr;
  }
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}

.meta-icon {
  font-size: 20px;
}

.meta-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.meta-label {
  font-size: 11px;
  color: var(--text-muted);
}

.meta-value {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
}
</style>
