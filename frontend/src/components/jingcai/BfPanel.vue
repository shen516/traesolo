<template>
  <div>
    <UpgradeHint
      v-if="match.oddsBfLocked"
      text="免费版仅展示胜/平/负其它三项 SP，升级专业版解锁全部比分赔率"
      style="margin-bottom: 10px;"
    />
    <div v-if="hasBf" class="bf-panel">
      <div v-for="row in BF_ROWS" :key="row.label" class="bf-row" :class="row.key">
        <span class="bf-label">{{ row.label }}</span>
        <button
          v-for="key in row.keys"
          :key="key"
          type="button"
          class="bf-cell"
          :class="{
            locked: isLocked(key),
            top3: isTop3(key),
            hit: showHit && isHit(key),
          }"
          disabled
        >
          <span class="bf-score">{{ key }}</span>
          <span class="bf-sp">{{ isLocked(key) ? '🔒' : fmtOdds(match.oddsBf[key]) }}</span>
        </button>
      </div>
    </div>
    <div v-else class="bf-empty">暂无比分赔率</div>
    <ScoreTop3Panel
      v-if="match.handicap != null && match.oddsSpfWin != null"
      :match-id="match.id"
      class="top3-block"
      @update="(scores) => $emit('top3', scores)"
    />
  </div>
</template>

<script setup>
/**
 * 竞彩比分赔率展开面板（主胜/平局/客胜三行 + 历史相似盘口 Top3）。
 * 在赛与历史模式共用；历史模式传 show-hit 高亮实际赛果。
 */
import { computed } from 'vue'
import { fmtOdds } from '@/utils/matchMeta'
import UpgradeHint from '@/components/UpgradeHint.vue'
import ScoreTop3Panel from '@/components/ScoreTop3Panel.vue'

const props = defineProps({
  match: { type: Object, required: true },
  /** { [matchId]: string[] } 相似盘口 Top3 比分键 */
  top3Scores: { type: Object, default: () => ({}) },
  showHit: { type: Boolean, default: false },
})

defineEmits(['top3'])

const BF_HOME = ['1:0', '2:0', '2:1', '3:0', '3:1', '3:2', '4:0', '4:1', '4:2', '5:0', '5:1', '5:2', '胜其它']
const BF_DRAW = ['0:0', '1:1', '2:2', '3:3', '平其它']
const BF_AWAY = ['0:1', '0:2', '1:2', '0:3', '1:3', '2:3', '0:4', '1:4', '2:4', '0:5', '1:5', '2:5', '负其它']
const BF_KNOWN = new Set([...BF_HOME, ...BF_DRAW, ...BF_AWAY])
const BF_FREE_KEYS = new Set(['胜其它', '平其它', '负其它'])

const BF_ROWS = [
  { key: 'home', label: '主胜', keys: BF_HOME },
  { key: 'draw', label: '平局', keys: BF_DRAW },
  { key: 'away', label: '客胜', keys: BF_AWAY },
]

const hasBf = computed(() =>
  props.match?.oddsBf && typeof props.match.oddsBf === 'object' && Object.keys(props.match.oddsBf).length > 0
)

function isLocked(key) {
  return !!(props.match?.oddsBfLocked && !BF_FREE_KEYS.has(key))
}

function isTop3(key) {
  return !!props.top3Scores?.[props.match.id]?.includes(key)
}

function actualScoreKey() {
  const m = props.match
  if (!m || m.status !== 'finished') return ''
  if (m.result == null || m.homeGoals == null || m.awayGoals == null) return ''
  const key = `${Number(m.homeGoals)}:${Number(m.awayGoals)}`
  if (BF_KNOWN.has(key)) return key
  if (m.homeGoals > m.awayGoals) return '胜其它'
  if (m.homeGoals === m.awayGoals) return '平其它'
  return '负其它'
}

function isHit(key) {
  return actualScoreKey() === key
}
</script>

<style scoped>
.bf-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bf-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.bf-label {
  width: 36px;
  flex-shrink: 0;
  font-size: 0.78rem;
  color: var(--text-muted);
}

.bf-row.home .bf-label { color: var(--color-green); }
.bf-row.draw .bf-label { color: var(--color-gold); }
.bf-row.away .bf-label { color: var(--color-red); }

.bf-cell {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 52px;
  padding: 4px 6px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: default;
  opacity: 1;
}

.bf-score {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.bf-sp {
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
  color: var(--color-gold);
}

.bf-cell.locked {
  opacity: 0.55;
  border-style: dashed;
}
.bf-cell.top3 {
  border-color: var(--color-blue);
  box-shadow: 0 0 0 1px var(--color-blue) inset;
}
.bf-cell.hit {
  border-color: var(--color-green);
  background: rgba(var(--color-green-rgb), 0.18);
  box-shadow: 0 0 0 1px var(--color-green) inset;
}
.bf-cell.locked .bf-sp {
  font-size: 0.75rem;
}
.top3-block {
  margin-top: 10px;
}
.bf-empty {
  color: var(--text-muted);
  font-size: 0.85rem;
  padding: 8px 0;
}

@media (max-width: 768px) {
  .bf-label {
    width: 100%;
    margin-bottom: 2px;
  }
}
</style>
