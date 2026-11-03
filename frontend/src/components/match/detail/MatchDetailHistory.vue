<template>
  <div class="match-detail-history">
    <div class="card odds-card">
      <div class="card-title">
        <span class="title-bar"></span>
        赔率时序（分析展示）
      </div>
      <p class="odds-disclaimer">仅用于观察市场共识变化，不构成投注建议。</p>
      <div v-if="hasAnyOdds" class="odds-current-block">
        <div class="odds-current">
          胜平负：胜 {{ fmtOdds(match.oddsNspfWin) }} / 平 {{ fmtOdds(match.oddsNspfDraw) }} / 负 {{ fmtOdds(match.oddsNspfLose) }}
        </div>
        <div class="odds-current">
          让球 {{ handicapLabel || '-' }}：胜 {{ fmtOdds(match.oddsSpfWin) }} / 平 {{ fmtOdds(match.oddsSpfDraw) }} / 负 {{ fmtOdds(match.oddsSpfLose) }}
        </div>
      </div>
      <UpgradeHint
        v-if="oddsSnapshotsLocked"
        text="赔率时序快照需专业版解锁"
        style="margin:8px 0;"
      />
      <div v-else-if="!oddsSnapshots.length" class="history-empty soft">暂无赔率快照（采集覆盖写赔率且发生变化时才会落库）</div>
      <div v-else class="odds-table-wrap">
        <table class="player-stats-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>让球</th>
              <th>胜</th>
              <th>平</th>
              <th>负</th>
              <th>来源</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in oddsSnapshots" :key="s.id">
              <td>{{ formatSnapshotTime(s.capturedAt || s.captured_at) }}</td>
              <td>{{ s.handicap ?? '-' }}</td>
              <td>{{ fmtOdds(s.oddsNspfWin || s.odds_nspf_win) }}</td>
              <td>{{ fmtOdds(s.oddsNspfDraw || s.odds_nspf_draw) }}</td>
              <td>{{ fmtOdds(s.oddsNspfLose || s.odds_nspf_lose) }}</td>
              <td>{{ s.source || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card history-card">
      <div class="card-title">
        <span class="title-bar"></span>
        历史交锋记录
      </div>
      <div v-if="!headToHead.length" class="history-empty soft">
        暂无两队完赛交锋记录
      </div>
      <div v-else class="history-list">
        <div v-for="(h, idx) in headToHead" :key="h.matchId || idx" class="history-item">
          <span class="history-date">{{ h.date || '-' }}</span>
          <span class="history-match">{{ h.match }}</span>
          <span class="history-score">{{ h.score }}</span>
          <span class="history-result" :class="resultClass(h.result)">
            {{ resultText(h.result) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import UpgradeHint from '@/components/UpgradeHint.vue'
import { fmtOdds } from '@/utils/matchMeta'
import {
  formatSnapshotTime,
  resultClass,
  resultText,
} from './matchDetailFormat'

defineProps({
  match: { type: Object, required: true },
  hasAnyOdds: { type: Boolean, default: false },
  handicapLabel: { type: [String, Number], default: '' },
  oddsSnapshots: { type: Array, default: () => [] },
  oddsSnapshotsLocked: { type: Boolean, default: false },
  headToHead: { type: Array, default: () => [] },
})
</script>

<style scoped>
.match-detail-history {
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

.odds-disclaimer {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0 0 10px;
}

.odds-current-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.odds-current {
  font-size: 13px;
  color: var(--text-primary);
}

.odds-table-wrap {
  overflow-x: auto;
}

.player-stats-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.player-stats-table th {
  padding: 8px 10px;
  text-align: center;
  color: var(--text-muted);
  font-weight: 600;
  border-bottom: 1px solid var(--border-color);
  white-space: nowrap;
}

.player-stats-table td {
  padding: 8px 10px;
  text-align: center;
  color: var(--text-primary);
  border-bottom: 1px solid rgba(30, 58, 95, 0.3);
}

.player-stats-table tbody tr:hover {
  background: var(--bg-hover);
}

.history-empty.soft {
  padding: 16px;
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-item {
  display: grid;
  grid-template-columns: 100px 1fr 80px 80px;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  transition: var(--transition);
}

.history-item:hover {
  border-color: rgba(var(--color-blue-rgb), 0.3);
  background: var(--bg-hover);
}

.history-date {
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'Consolas', monospace;
}

.history-match {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
}

.history-score {
  font-size: 14px;
  color: var(--color-gold);
  font-weight: 700;
  font-family: 'Consolas', monospace;
  text-align: center;
}

.history-result {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-align: center;
}

.result-home {
  background: rgba(var(--color-blue-rgb), 0.15);
  color: var(--color-blue);
}

.result-draw {
  background: rgba(var(--color-orange-rgb), 0.15);
  color: var(--color-orange);
}

.result-away {
  background: rgba(var(--color-red-rgb), 0.15);
  color: var(--color-red);
}
</style>
