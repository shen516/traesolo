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
        <div class="actual-score">
          <span class="score-home">{{ match.homeGoals }}</span>
          <span class="score-separator">-</span>
          <span class="score-away">{{ match.awayGoals }}</span>
        </div>
        <div class="result-badge" :class="resultBadgeClass(match.result)">
          {{ resultText(match.result) }}
        </div>
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

    <div v-if="density === 'full'" class="stats-section">
      <div class="stat-item">
        <span class="stat-icon">⚽</span>
        <span class="stat-label">总进球</span>
        <span class="stat-value">{{ match.totalGoals }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-icon">🏟️</span>
        <span class="stat-label">场地</span>
        <span class="stat-value">{{ match.venue || '-' }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-icon">🌤️</span>
        <span class="stat-label">天气</span>
        <span class="stat-value">{{ match.weather || '-' }}</span>
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

    <div class="prediction-review">
      <template v-if="match.prediction.hasPrediction">
        <div class="review-top">
          <span class="review-label">{{ match.prediction.afterMatch ? '赛后补算' : '赛前预测' }}</span>
          <span class="tag" :class="hitTagClass(match)">{{ hitText(match) }}</span>
        </div>
        <div class="review-scores">
          <div class="review-score-item">
            <span class="review-k">预测</span>
            <span class="review-v pred">{{ match.prediction.mainScore }}</span>
          </div>
          <div class="review-score-item">
            <span class="review-k">实际</span>
            <span class="review-v actual">{{ match.homeGoals }}-{{ match.awayGoals }}</span>
          </div>
        </div>
        <div v-if="density === 'full'" class="review-probs">
          <span>主胜 {{ pct(match.prediction.homeWinProb) }}</span>
          <span>平 {{ pct(match.prediction.drawProb) }}</span>
          <span>客胜 {{ pct(match.prediction.awayWinProb) }}</span>
        </div>
        <p v-if="match.prediction.tendency" class="review-tendency">{{ match.prediction.tendency }}</p>
      </template>
      <div v-else class="review-empty">赛前未计算预测</div>
    </div>

    <div class="card-footer">
      <div class="match-status">
        <span class="status-icon">✅</span>
        已结束
      </div>
      <button class="btn btn-outline btn-sm view-detail-btn">查看详情</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { hitText, hitTagClass } from '@/utils/adapters'
import MatchOddsBrief from '@/components/match/MatchOddsBrief.vue'
import {
  getStageLabel,
  stageTagClass,
  resultBadgeClass,
  resultText,
  pct,
  marketTendencyTagClass,
  deltaLevelTagClass,
} from '@/utils/matchMeta'

const props = defineProps({
  match: { type: Object, required: true },
  league: { type: Object, default: () => ({ name: '未知联赛', icon: '⚽' }) },
  homeTeam: { type: Object, default: () => ({ name: '未知', short: '未知', logo: '⚪' }) },
  awayTeam: { type: Object, default: () => ({ name: '未知', short: '未知', logo: '⚪' }) },
  density: { type: String, default: 'compact' },
})

defineEmits(['detail'])

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
          : '偏差小',
      cls: deltaLevelTagClass(a.deltaLevel),
      title: '市场隐含 vs 赛前模型',
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
  gap: 12px;
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
  background: linear-gradient(90deg, transparent, var(--color-green), transparent);
  opacity: 0;
  transition: var(--transition);
}
.match-card:hover {
  border-color: rgba(0, 255, 128, 0.4);
  box-shadow: 0 0 24px rgba(0, 255, 128, 0.2), 0 4px 20px rgba(0, 0, 0, 0.4);
  transform: translateY(-2px);
}
.match-card:hover::before { opacity: 1; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 8px;
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
.stage-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}
.tag-group { background: rgba(var(--color-blue-rgb), 0.15); color: var(--color-blue); border: 1px solid rgba(var(--color-blue-rgb), 0.3); }
.tag-round16 { background: rgba(16, 185, 129, 0.15); color: var(--color-green); border: 1px solid rgba(16, 185, 129, 0.3); }
.tag-quarter { background: rgba(245, 158, 11, 0.15); color: var(--color-orange); border: 1px solid rgba(245, 158, 11, 0.3); }
.tag-semi { background: rgba(236, 72, 153, 0.15); color: var(--color-red); border: 1px solid rgba(236, 72, 153, 0.3); }
.tag-third { background: rgba(251, 191, 36, 0.15); color: var(--color-yellow); border: 1px solid rgba(251, 191, 36, 0.3); }
.tag-final { background: rgba(139, 92, 246, 0.15); color: var(--color-purple); border: 1px solid rgba(139, 92, 246, 0.3); }
.tag-league { background: rgba(148, 163, 184, 0.15); color: var(--text-secondary); border: 1px solid rgba(148, 163, 184, 0.3); }
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
.actual-score {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: 22px;
  font-weight: 800;
  font-family: 'Consolas', 'Microsoft YaHei', sans-serif;
}
.score-home { color: var(--color-green); }
.score-separator { font-size: 16px; color: var(--text-muted); }
.score-away { color: var(--color-red); }
.odds-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.result-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}
.result-home { background: rgba(0, 255, 128, 0.2); color: var(--color-green); }
.result-away { background: rgba(255, 100, 100, 0.2); color: var(--color-red); }
.result-draw { background: rgba(255, 180, 50, 0.2); color: var(--color-orange); }
.stats-section {
  display: flex;
  justify-content: space-around;
  padding: 10px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
}
.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  font-size: 11px;
}
.stat-icon { font-size: 14px; }
.stat-label { color: var(--text-muted); }
.stat-value { color: var(--text-primary); font-weight: 600; }
.prediction-review {
  padding: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}
.review-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.review-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.review-scores {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 8px;
}
.review-score-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
  background: var(--bg-card);
  border-radius: 6px;
}
.review-k { font-size: 11px; color: var(--text-muted); }
.review-v {
  font-size: 18px;
  font-weight: 800;
  font-family: Consolas, 'Microsoft YaHei', sans-serif;
}
.review-v.pred { color: var(--color-gold); }
.review-v.actual { color: var(--color-green); }
.review-probs {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
}
.review-tendency {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-primary);
  line-height: 1.4;
}
.review-empty {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  padding: 4px 0;
}
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 10px;
  border-top: 1px solid var(--border-color);
}
.match-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-green);
}
.view-detail-btn {
  font-size: 11px;
  padding: 4px 12px;
}
</style>
