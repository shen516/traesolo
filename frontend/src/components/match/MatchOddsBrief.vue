<template>
  <div
    class="odds-brief"
    :class="{ empty: !hasOdds }"
    title="竞彩参考，仅供分析，不构成投注建议"
  >
    <div class="odds-brief-head">
      <span class="odds-brief-title">竞彩</span>
      <span v-if="!hasOdds" class="odds-brief-empty">暂无赔率</span>
    </div>
    <template v-if="hasOdds">
      <div v-if="hasNspf" class="odds-brief-row">
        <span class="odds-k">胜平负</span>
        <span class="odds-vals">
          <span class="ov"><i>胜</i>{{ fmtOdds(match.oddsNspfWin) }}</span>
          <span class="ov"><i>平</i>{{ fmtOdds(match.oddsNspfDraw) }}</span>
          <span class="ov"><i>负</i>{{ fmtOdds(match.oddsNspfLose) }}</span>
        </span>
      </div>
      <div v-if="hasSpf || handicapLabel" class="odds-brief-row">
        <span class="odds-k">让球 {{ handicapLabel || '-' }}</span>
        <span class="odds-vals">
          <span class="ov"><i>胜</i>{{ fmtOdds(match.oddsSpfWin) }}</span>
          <span class="ov"><i>平</i>{{ fmtOdds(match.oddsSpfDraw) }}</span>
          <span class="ov"><i>负</i>{{ fmtOdds(match.oddsSpfLose) }}</span>
        </span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fmtOdds, formatHandicap, hasMatchOdds } from '@/utils/matchMeta'

const props = defineProps({
  match: { type: Object, required: true },
})

const hasOdds = computed(() => hasMatchOdds(props.match))
const hasNspf = computed(() =>
  [props.match?.oddsNspfWin, props.match?.oddsNspfDraw, props.match?.oddsNspfLose]
    .some((v) => v != null && v !== '')
)
const hasSpf = computed(() =>
  [props.match?.oddsSpfWin, props.match?.oddsSpfDraw, props.match?.oddsSpfLose]
    .some((v) => v != null && v !== '')
)
const handicapLabel = computed(() => formatHandicap(props.match?.handicap))
</script>

<style scoped>
.odds-brief {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}
.odds-brief.empty {
  opacity: 0.75;
}
.odds-brief-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.odds-brief-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-gold);
  letter-spacing: 0.5px;
}
.odds-brief-empty {
  font-size: 11px;
  color: var(--text-muted);
}
.odds-brief-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  line-height: 1.35;
}
.odds-k {
  flex-shrink: 0;
  color: var(--text-muted);
  font-weight: 600;
  min-width: 4.5em;
}
.odds-vals {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  color: var(--text-primary);
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-weight: 600;
}
.ov i {
  font-style: normal;
  margin-right: 3px;
  color: var(--text-muted);
  font-weight: 500;
  font-size: 11px;
}
</style>
