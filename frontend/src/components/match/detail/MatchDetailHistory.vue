<template>
  <div class="match-detail-history">
    <div class="card odds-card">
      <div class="card-title">
        <span class="title-bar"></span>
        赔率时序（分析展示）
      </div>
      <p class="odds-disclaimer">仅用于观察市场共识变化与模型概率对照，不构成投注建议。</p>
      <div v-if="hasAnyOdds" class="odds-current-block">
        <div class="odds-current">
          胜平负：胜 {{ fmtOdds(match.oddsNspfWin) }} / 平 {{ fmtOdds(match.oddsNspfDraw) }} / 负 {{ fmtOdds(match.oddsNspfLose) }}
        </div>
        <div class="odds-current">
          让球 {{ handicapLabel || '-' }}：胜 {{ fmtOdds(match.oddsSpfWin) }} / 平 {{ fmtOdds(match.oddsSpfDraw) }} / 负 {{ fmtOdds(match.oddsSpfLose) }}
        </div>
      </div>

      <div v-if="modelCompare" class="model-compare-block">
        <div class="compare-title">模型概率 vs 最新市场隐含</div>
        <div class="compare-row">
          <span class="cmp-label">模型</span>
          <span>主 {{ pct1(modelCompare.model.home) }}</span>
          <span>平 {{ pct1(modelCompare.model.draw) }}</span>
          <span>客 {{ pct1(modelCompare.model.away) }}</span>
        </div>
        <div class="compare-row">
          <span class="cmp-label">市场</span>
          <span>主 {{ pct1(modelCompare.implied.home) }}</span>
          <span>平 {{ pct1(modelCompare.implied.draw) }}</span>
          <span>客 {{ pct1(modelCompare.implied.away) }}</span>
        </div>
        <div class="compare-row deltas" v-if="modelCompare.vs">
          <span class="cmp-label">偏差</span>
          <span :class="deltaClass(modelCompare.vs.deltaHome)">{{ signedPt(modelCompare.vs.deltaHome) }}</span>
          <span :class="deltaClass(modelCompare.vs.deltaDraw)">{{ signedPt(modelCompare.vs.deltaDraw) }}</span>
          <span :class="deltaClass(modelCompare.vs.deltaAway)">{{ signedPt(modelCompare.vs.deltaAway) }}</span>
        </div>
        <div class="compare-meta" v-if="modelCompare.vs">
          最大偏差 {{ modelCompare.vs.maxAbsDeltaPct.toFixed(1) }}pt（{{ modelCompare.vs.maxSideLabel }}）
          · 倾向{{ modelCompare.vs.agreeTendency ? '一致' : '不一致' }}
          · overround {{ modelCompare.implied.overroundPct.toFixed(1) }}%
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
              <th>隐含主/平/客</th>
              <th>vs 模型</th>
              <th>来源</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in snapshotRows" :key="row.id">
              <td>{{ formatSnapshotTime(row.capturedAt) }}</td>
              <td>{{ row.handicap ?? '-' }}</td>
              <td>{{ fmtOdds(row.win) }}</td>
              <td>{{ fmtOdds(row.draw) }}</td>
              <td>{{ fmtOdds(row.lose) }}</td>
              <td class="impl-cell">
                <template v-if="row.implied">
                  {{ pct1(row.implied.home) }} / {{ pct1(row.implied.draw) }} / {{ pct1(row.implied.away) }}
                </template>
                <template v-else>-</template>
              </td>
              <td class="vs-cell">
                <template v-if="row.vs">
                  <span :class="'level-' + row.vs.level">
                    {{ row.vs.maxAbsDeltaPct.toFixed(1) }}pt
                  </span>
                  <span class="agree" :class="{ ok: row.vs.agreeTendency }">
                    {{ row.vs.agreeTendency ? '同向' : '异向' }}
                  </span>
                </template>
                <template v-else>-</template>
              </td>
              <td>{{ row.source || '-' }}</td>
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
import { computed } from 'vue'
import UpgradeHint from '@/components/UpgradeHint.vue'
import { fmtOdds, impliedFromSp, compareImpliedToModel } from '@/utils/matchMeta'
import {
  formatSnapshotTime,
  resultClass,
  resultText,
} from './matchDetailFormat'

const props = defineProps({
  match: { type: Object, required: true },
  hasAnyOdds: { type: Boolean, default: false },
  handicapLabel: { type: [String, Number], default: '' },
  oddsSnapshots: { type: Array, default: () => [] },
  oddsSnapshotsLocked: { type: Boolean, default: false },
  headToHead: { type: Array, default: () => [] },
})

function modelProbs() {
  const p = props.match?.prediction
  if (!p) return null
  const home = Number(p.homeWinProb)
  const draw = Number(p.drawProb)
  const away = Number(p.awayWinProb)
  if (![home, draw, away].every((x) => Number.isFinite(x))) return null
  return { home, draw, away }
}

function pct1(v) {
  if (v == null || !Number.isFinite(Number(v))) return '-'
  return `${(Number(v) * 100).toFixed(1)}%`
}

function signedPt(v) {
  if (v == null || !Number.isFinite(Number(v))) return '-'
  const pt = Number(v) * 100
  const sign = pt > 0 ? '+' : ''
  return `${sign}${pt.toFixed(1)}pt`
}

function deltaClass(v) {
  if (v == null || !Number.isFinite(Number(v))) return ''
  if (Number(v) > 0.01) return 'pos'
  if (Number(v) < -0.01) return 'neg'
  return ''
}

const modelCompare = computed(() => {
  const model = modelProbs()
  if (!model) return null
  const m = props.match
  const implied = impliedFromSp(m.oddsNspfWin, m.oddsNspfDraw, m.oddsNspfLose)
    || impliedFromSp(m.oddsSpfWin, m.oddsSpfDraw, m.oddsSpfLose)
  if (!implied) return null
  return {
    model,
    implied,
    vs: compareImpliedToModel(implied, model),
  }
})

const snapshotRows = computed(() => {
  const model = modelProbs()
  return (props.oddsSnapshots || []).map((s) => {
    const win = s.oddsNspfWin ?? s.odds_nspf_win
    const draw = s.oddsNspfDraw ?? s.odds_nspf_draw
    const lose = s.oddsNspfLose ?? s.odds_nspf_lose
    const implied = impliedFromSp(win, draw, lose)
    return {
      id: s.id,
      capturedAt: s.capturedAt || s.captured_at,
      handicap: s.handicap,
      win,
      draw,
      lose,
      source: s.source,
      implied,
      vs: compareImpliedToModel(implied, model),
    }
  })
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

.model-compare-block {
  margin: 8px 0 14px;
  padding: 12px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.compare-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.compare-row {
  display: grid;
  grid-template-columns: 48px repeat(3, 1fr);
  gap: 8px;
  font-size: 13px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.compare-row.deltas {
  font-family: 'Consolas', monospace;
  font-size: 12px;
}

.cmp-label {
  color: var(--text-muted);
  font-weight: 600;
}

.compare-row .pos { color: var(--color-orange); }
.compare-row .neg { color: var(--color-blue); }

.compare-meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-muted);
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

.impl-cell {
  font-family: 'Consolas', monospace;
  font-size: 11px;
  white-space: nowrap;
}

.vs-cell {
  white-space: nowrap;
}

.vs-cell .level-low { color: var(--color-blue); }
.vs-cell .level-mid { color: var(--color-orange); }
.vs-cell .level-high { color: var(--color-red); font-weight: 700; }

.vs-cell .agree {
  margin-left: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.vs-cell .agree.ok {
  color: var(--color-blue);
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
