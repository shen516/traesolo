<template>
  <div class="card player-stats-card" v-if="visible">
    <div class="card-title player-stats-header">
      <div class="player-stats-title-wrap">
        <span class="title-bar"></span>
        逐场球员统计
      </div>
      <button
        class="export-btn recalc-btn stats-crawl-btn"
        :disabled="crawling"
        @click="$emit('crawl')"
      >
        {{ crawling ? '采集中...' : '采集本场统计' }}
      </button>
      <button
        v-if="sides.some((s) => s.stats.length)"
        class="export-btn recalc-btn stats-crawl-btn"
        @click="showDetail = !showDetail"
      >
        {{ showDetail ? '精简列' : '全部列' }}
      </button>
    </div>
    <div v-if="error" class="state-banner error-banner stats-error">{{ error }}</div>

    <div v-if="loading" class="player-stats-loading">
      <div class="loading-spinner small-spinner"></div>
      <span>加载球员统计...</span>
    </div>

    <div v-else-if="!sides.some((s) => s.stats.length)" class="player-stats-empty">
      <div class="empty-icon">📊</div>
      <p>暂无逐场球员统计数据</p>
      <p class="empty-hint">点击「采集本场统计」从 ESPN 获取，或在定时任务中批量补全</p>
    </div>

    <div v-else class="player-stats-grid">
      <div class="player-stats-team" v-for="side in sides" :key="side.key">
        <div class="team-stats-title">
          <span class="team-stats-label" :class="side.key">{{ side.label }}</span>
          <span class="team-stats-name">{{ side.teamName }}</span>
          <span class="team-stats-count">{{ side.stats.length }} 人出场</span>
        </div>
        <div class="player-stats-table-wrap">
          <table class="player-stats-table">
            <thead>
              <tr>
                <th>球员</th>
                <th>位置</th>
                <th>进球</th>
                <th>助攻</th>
                <th>射门</th>
                <th>射正</th>
                <template v-if="showDetail">
                  <th>传球</th>
                  <th>抢断</th>
                  <th>黄牌</th>
                </template>
                <th>时间</th>
                <th>评分</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in side.stats" :key="p.playerId">
                <td class="col-player">
                  <span class="jersey-num" v-if="p.jerseyNumber">{{ p.jerseyNumber }}</span>
                  <span class="player-name">{{ p.playerName || p.playerId }}</span>
                </td>
                <td><span class="position-badge">{{ positionText(p.position) }}</span></td>
                <td class="text-gold">{{ p.goals || '-' }}</td>
                <td class="text-blue">{{ p.assists || '-' }}</td>
                <td>{{ p.shots ?? '-' }}</td>
                <td>{{ p.shotsOnTarget ?? '-' }}</td>
                <template v-if="showDetail">
                  <td>{{ p.passes ?? '-' }}</td>
                  <td>{{ p.tackles ?? '-' }}</td>
                  <td :class="{ 'text-orange': p.yellowCards > 0 }">{{ p.yellowCards || '-' }}</td>
                </template>
                <td>{{ p.minutesPlayed ? p.minutesPlayed + "'" : '-' }}</td>
                <td class="text-gold rating-cell">{{ p.rating ? p.rating.toFixed(1) : '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { positionText } from './matchDetailFormat'

defineProps({
  visible: { type: Boolean, default: true },
  sides: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  crawling: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

defineEmits(['crawl'])

const showDetail = ref(false)
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

.player-stats-header {
  justify-content: space-between;
}

.player-stats-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.stats-crawl-btn {
  padding: 6px 14px;
  font-size: 12px;
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
}

.player-stats-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 32px;
  color: var(--text-secondary);
  font-size: 13px;
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid var(--border-color);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.small-spinner {
  width: 24px;
  height: 24px;
  border-width: 3px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.player-stats-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  gap: 8px;
  color: var(--text-secondary);
}

.player-stats-empty .empty-icon {
  font-size: 40px;
  opacity: 0.5;
}

.player-stats-empty .empty-hint {
  font-family: inherit;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}

.stats-error {
  margin-bottom: 12px;
}

.player-stats-grid {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.team-stats-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}

.team-stats-label {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}

.team-stats-label.home {
  background: rgba(var(--color-blue-rgb), 0.15);
  color: var(--color-blue);
}

.team-stats-label.away {
  background: rgba(var(--color-red-rgb), 0.15);
  color: var(--color-red);
}

.team-stats-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.team-stats-count {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-muted);
}

.player-stats-table-wrap {
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

.col-player {
  text-align: left !important;
  white-space: nowrap;
}

.jersey-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  margin-right: 6px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
}

.col-player .player-name {
  font-weight: 600;
}

.position-badge {
  font-size: 11px;
  padding: 2px 6px;
  background: rgba(var(--color-blue-rgb), 0.08);
  border-radius: 4px;
  color: var(--color-blue);
}

.rating-cell {
  font-weight: 700;
  font-family: 'Consolas', monospace;
}
</style>
